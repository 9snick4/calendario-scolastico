# app/utils/ordinary_placement.py

from math import ceil

from app.utils.orario_utils import slot_libero, piazza_blocco
from app.utils.utils_scheduler import compatta_giornata, crea_buco_in_giornata
import app.utils.occupazione as occ


# ------------------------------------------------------------
# CONTROLLO UNIFICATO SLOT
# ------------------------------------------------------------
def slot_assegnabile(griglia, classe_id, docente_id, data, ora, docente_ok, giorno_it):
    slot = griglia[data][ora]

    # Slot deve essere vuoto
    if slot is not None:
        return False

    # Classe non deve essere occupata globalmente
    if occ.classe_occupata(classe_id, data, ora):
        return False

    # Docente libero globalmente
    if docente_id and not docente_disponibile_global(docente_id, data, ora):
        return False

    # Vincoli docente
    if docente_id and not docente_ok(docente_id, data, giorno_it, ora, 1):
        return False

    return True

def giornata_valida(griglia, data, ore_giornaliere, g=None):
    """
    Una giornata è valida solo se contiene almeno 4 ore consecutive.
    Le giornate con meno di 4 ore NON sono valide.
    Eccezioni: giorni speciali e giorni fissi.
    """

    # Eccezioni: speciali, fissi, stage, festa
    if g and (g.get("speciale") or g.get("fisso") or g.get("tipo") in ("SPECIALE", "STAGE", "FESTA")):
        return True

    # Ore presenti
    ore = [h for h in range(ore_giornaliere) if griglia[data][h] is not None]

    # Meno di 4 ore → NON valida
    if len(ore) < 4:
        return False

    # Cerca un blocco di 4 consecutive
    consecutive = 1
    for i in range(1, len(ore)):
        if ore[i] == ore[i-1] + 1:
            consecutive += 1
            if consecutive >= 4:
                return True
        else:
            consecutive = 1

    # Nessun blocco di 4 → NON valida
    return False



def giornata_legale(griglia, data, ore_giornaliere):
    """
    Una giornata è legale se:
    - ha meno di 4 ore → non imponiamo compattezza
    - oppure ha almeno un blocco di 4 ore consecutive
    """
    ore_presenti = [
        h for h in range(ore_giornaliere)
        if griglia[data][h] is not None
    ]

    if len(ore_presenti) < 4:
        return True  # non imponiamo 4 consecutive se la giornata è "leggera"

    consecutive = 1
    for i in range(1, len(ore_presenti)):
        if ore_presenti[i] == ore_presenti[i-1] + 1:
            consecutive += 1
            if consecutive >= 4:
                return True
        else:
            consecutive = 1

    return False

from datetime import date

def tutte_giornate_legali(griglie, settimane_classe, classe):
    ore_giornaliere = classe.ore_massime_giornaliere or 6

    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
        griglia = griglie[key]

        for g in giorni:
            data = g["data"]

            # 🔥 ECCEZIONI: giorni speciali, fissi, stage, festa
            if g.get("speciale") or g.get("fisso") or g.get("tipo") in ("SPECIALE", "STAGE", "FESTA"):
                continue

            # Ore presenti nella giornata
            ore_presenti = [
                h for h in range(ore_giornaliere)
                if griglia[data][h] is not None
            ]

            # 🔥 PRIMA DEL 1 MARZO → giornata deve essere PIENA
            if data < date(data.year, 3, 1):
                if len(ore_presenti) != ore_giornaliere:
                    return False
                continue

            # 🔥 DOPO IL 1 MARZO → almeno 4 ore consecutive
            if not giornata_valida(griglia, data, ore_giornaliere, g):
                return False

    return True


# ------------------------------------------------------------
# 0) CHECK / INIT OCCUPAZIONE GLOBALE DOCENTE
# ------------------------------------------------------------
def docente_disponibile_global(docente_id, data, ora):
    if docente_id is None:
        return True
    return occ.docente_libero(docente_id, data, ora)


def inizializza_occupazione_globale_da_locale(occupazione_docenti):
    # NON cancellare la globale: deve già contenere i piazzamenti fissi e speciali
    for docente_id, giorni_dict in occupazione_docenti.items():
        for data, ore_set in giorni_dict.items():
            for ora in ore_set:
                occ.occupa(docente_id, None, data, ora)


# ------------------------------------------------------------
# 1) CALCOLA FABBISOGNO SETTIMANALE
# ------------------------------------------------------------
def calcola_fabbisogno_settimanale(materie_info, settimane_classe):
    num_settimane = len(settimane_classe) or 1
    fabbisogno = {}
    for mid, info in materie_info.items():
        debito = info.get("debito_residuo", 0)
        if debito > 0:
            fabbisogno[mid] = ceil(debito / num_settimane)
    return fabbisogno


# ------------------------------------------------------------
# 2) DISTRIBUISCI FABBISOGNO
# ------------------------------------------------------------
def distribuisci_fabbisogno(griglie, settimane_classe, classe, materie_info, docente_ok):

    fabbisogno = calcola_fabbisogno_settimanale(materie_info, settimane_classe)
    ore_giornaliere = classe.ore_massime_giornaliere or 6

    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
        griglia = griglie[key]

        for mid, ore_sett in fabbisogno.items():
            info_m = materie_info[mid]
            docente_id = info_m.get("docente_id")
            docente_nome = info_m.get("docente_nome", "")
            nome_materia = info_m.get("nome", "").upper()

            blocco = info_m.get("blocco_orario", 1)
            if blocco == 1 and "EDUCAZIONE" in nome_materia and "MOTORIA" in nome_materia:
                blocco = 2

            for _ in range(ore_sett):
                if info_m["debito_residuo"] <= 0:
                    break

                piazzato = False

                for g in giorni:
                    data = g["data"]
                    giorno_it = g["giorno_it"]

                    # Salta solo STAGE e FESTA
                    if g.get("tipo") in ("STAGE", "FESTA"):
                        continue

                    # NON piazzare sopra slot speciali
                    if g.get("speciale"):
                        continue

                    for ora in range(ore_giornaliere - (blocco - 1)):

                        # Controllo blocco intero
                        ok = True
                        for h in range(ora, ora + blocco):
                            if not slot_assegnabile(griglia, classe.id, docente_id, data, h, docente_ok, giorno_it):
                                ok = False
                                break
                        if not ok:
                            continue

                        # Evita buchi
                        if crea_buco_in_giornata(griglia, data, ora, blocco):
                            continue

                        # PIAZZA
                        piazza_blocco(
                            griglia,
                            data,
                            ora,
                            blocco,
                            info_m["nome"],
                            docente_nome,
                            docente_id,
                            None,
                            classe_id=classe.id,
                            materia_id=mid,
                            tipo="ORDINARIO",
                            origine="ordinario"
                        )

                        # Aggiorna occupazione globale
                        if docente_id is not None:
                            for h in range(ora, ora + blocco):
                                occ.occupa(docente_id, classe.id, data, h)

                        info_m["debito_residuo"] -= blocco
                        info_m["ore_assegnate"] += blocco
                        piazzato = True
                        break

                    if piazzato:
                        break

# ------------------------------------------------------------
# 3) COMPATTAZIONE LEGGERA
# ------------------------------------------------------------
def compatta_settimane(griglie, settimane_classe):
    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
        griglia = griglie[key]
        for g in giorni:
            compatta_giornata(griglia, g["data"])


# ------------------------------------------------------------
# 4) UTILITY
# ------------------------------------------------------------
def count_ore_docente_in_classe(docente_id, griglia, data, ore_giornaliere):
    if docente_id is None:
        return 0
    return sum(
        1 for h in range(ore_giornaliere)
        if isinstance(griglia[data][h], dict)
        and griglia[data][h].get("docente_id") == docente_id
    )


def crea_buco_docente(docente_id, data, ora):
    occ_doc = occ.OCCUPAZIONE_DOCENTI_GLOBALE.get(docente_id, {})
    ore = occ_doc.get(data, {})
    if ora not in ore:
        return False
    ore_list = sorted(ore.keys())
    return any(h < ora for h in ore_list) and any(h > ora for h in ore_list)


def count_ore_in_giornata(griglia, data, ore_giornaliere):
    return sum(1 for h in range(ore_giornaliere) if griglia[data][h] is not None)


# ------------------------------------------------------------
# 5) NUOVA PASSATA: GARANTISCI 4 ORE CONSECUTIVE
# ------------------------------------------------------------
from datetime import date

def garantisci_quattro_ore_consecutive(griglie, settimane_classe, classe, materie_info, docente_ok):

    changed = False
    ore_giornaliere = classe.ore_massime_giornaliere or 6

    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
        griglia = griglie[key]

        for g in giorni:
            data = g["data"]
            giorno_it = g["giorno_it"]

            # 🔥 NON toccare giorni speciali, fissi, stage, festa
            if g.get("speciale") or g.get("fisso") or g.get("tipo") in ("SPECIALE", "STAGE", "FESTA"):
                continue

            # 🔥 Prima del 1 marzo → NON fare nulla
            if data < date(data.year, 3, 1):
                continue

            # 🔥 Dopo il 1 marzo → giornata deve avere almeno 4 consecutive
            if giornata_valida(griglia, data, ore_giornaliere, g):
                continue  # già valida

            # Ore presenti
            ore_presenti = [h for h in range(ore_giornaliere) if griglia[data][h] is not None]
            if len(ore_presenti) < 4:
                continue  # ci penserà backfill

            # 🔥 Obiettivo: compattare le ore presenti in un blocco di 4 consecutive
            target = ore_presenti[0]

            for h in ore_presenti:
                if h == target:
                    target += 1
                    continue

                slot = griglia[data][h]

                # NON spostare slot speciali
                if slot.get("origine") == "speciale" or slot.get("tipo") == "SPECIALE":
                    continue

                docente_id = slot.get("docente_id")

                # Controlli docente
                if docente_id and not docente_ok(docente_id, data, giorno_it, target, 1):
                    continue
                if docente_id and not docente_disponibile_global(docente_id, data, target):
                    continue

                # Classe libera
                if occ.classe_occupata(classe.id, data, target):
                    continue

                # 🔥 SPOSTAMENTO REALE
                piazza_blocco(
                    griglia,
                    data,
                    target,
                    1,
                    slot["materia"],
                    slot["docente"],
                    docente_id,
                    None,
                    classe_id=classe.id,
                    materia_id=slot.get("materia_id"),
                    tipo="ORDINARIO",
                    origine="4consecutive"
                )

                # Libera slot originale
                griglia[data][h] = None
                if docente_id:
                    occ.libera(docente_id, data, h)

                changed = True
                target += 1

    return changed


# ------------------------------------------------------------
# 6) COMPATTAZIONE AGGRESSIVA — PRENDE DAL FONDO DELL'ANNO
# ------------------------------------------------------------
def compattazione_aggressiva(griglie, settimane_classe, classe, materie_info, docente_ok):

    changed = False
    ore_giornaliere = classe.ore_massime_giornaliere or 6

    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
        griglia = griglie[key]

        for g in giorni:
            data = g["data"]
            giorno_it = g["giorno_it"]

            # 🔥 NON toccare giorni speciali, fissi, stage, festa
            if g.get("speciale") or g.get("fisso") or g.get("tipo") in ("SPECIALE", "STAGE", "FESTA"):
                continue

            # 🔥 Prima del 1 marzo → giornata deve essere piena
            if data < date(data.year, 3, 1):
                def giornata_target_valida():
                    ore_presenti = [h for h in range(ore_giornaliere) if griglia[data][h] is not None]
                    return len(ore_presenti) == ore_giornaliere
            else:
                # 🔥 Dopo il 1 marzo → almeno 4 consecutive
                def giornata_target_valida():
                    return giornata_valida(griglia, data, ore_giornaliere, g)

            for ora in range(ore_giornaliere):

                # NON piazzare sopra slot speciali
                if griglia[data][ora] and griglia[data][ora].get("origine") == "speciale":
                    continue

                # Slot deve essere vuoto
                if griglia[data][ora] is not None:
                    continue

                # Classe libera
                if occ.classe_occupata(classe.id, data, ora):
                    continue

                # 🔥 Se piazzare qui NON renderebbe valida la giornata → skip
                # (controllo fatto dopo aver trovato un candidato)
                # quindi per ora NON controlliamo qui

                trovato = False

                # Cerchiamo nel futuro
                for future_key in sorted(settimane_classe.keys(), reverse=True):
                    if future_key <= key:
                        continue

                    future_giorni = sorted(
                        settimane_classe[future_key],
                        key=lambda x: x["data"],
                        reverse=True
                    )
                    future_griglia = griglie[future_key]

                    for fg in future_giorni:
                        f_data = fg["data"]

                        # NON toccare giorni speciali, fissi, stage, festa
                        if fg.get("speciale") or fg.get("fisso") or fg.get("tipo") in ("SPECIALE", "STAGE", "FESTA"):
                            continue

                        for f_ora in range(ore_giornaliere - 1, -1, -1):

                            slot = future_griglia[f_data][f_ora]
                            if slot is None:
                                continue

                            # NON prendere slot speciali
                            if slot.get("origine") == "speciale" or slot.get("tipo") == "SPECIALE":
                                continue

                            # NON prendere fissi, professionali, doc est
                            if slot.get("fisso"):
                                continue
                            if slot.get("tipo") in ("STAGE", "FESTA", "PROFESSIONALE"):
                                continue
                            if slot.get("origine") in ("fisso",):
                                continue
                            if slot.get("docente") and "DOC EST" in slot.get("docente"):
                                continue

                            docente_id = slot.get("docente_id")
                            materia = slot.get("materia")

                            # Blocchi > 1 non spostabili
                            mid = next((m for m, info in materie_info.items() if info["nome"] == materia), None)
                            if mid:
                                blocco = materie_info[mid].get("blocco_orario", 1)
                                if blocco > 1:
                                    continue

                            # Controllo slot destinazione
                            if not slot_assegnabile(griglia, classe.id, docente_id, data, ora, docente_ok, giorno_it):
                                continue

                            # 🔥 Controllo che lo spostamento renda valida la giornata
                            # Simuliamo lo spostamento
                            griglia[data][ora] = slot
                            future_griglia[f_data][f_ora] = None

                            if not giornata_target_valida():
                                # rollback simulazione
                                future_griglia[f_data][f_ora] = slot
                                griglia[data][ora] = None
                                continue

                            # rollback simulazione prima dello spostamento reale
                            future_griglia[f_data][f_ora] = slot
                            griglia[data][ora] = None

                            # 🔥 SPOSTAMENTO REALE
                            piazza_blocco(
                                griglia,
                                data,
                                ora,
                                1,
                                slot["materia"],
                                slot["docente"],
                                docente_id,
                                None,
                                classe_id=classe.id,
                                materia_id=slot.get("materia_id"),
                                tipo="ORDINARIO",
                                origine="compattazione"
                            )

                            future_griglia[f_data][f_ora] = None

                            if docente_id:
                                occ.libera(docente_id, f_data, f_ora)
                                occ.occupa(docente_id, classe.id, data, ora)

                            changed = True
                            trovato = True
                            break

                        if trovato:
                            break
                    if trovato:
                        break

    return changed


# -----------------------
# 7 Riequilibra giornate
# -----------------------

def riequilibra_giornate(griglie, settimane_classe, classe, materie_info, docente_ok):

    changed = False
    ore_giornaliere = classe.ore_massime_giornaliere or 6

    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
        griglia = griglie[key]

        # Calcola carichi giornalieri (solo giorni normali)
        carichi = {
            g["data"]: sum(1 for h in range(ore_giornaliere) if griglia[g["data"]][h] is not None)
            for g in giorni
            if not g.get("speciale") and not g.get("fisso") and g.get("tipo") not in ("STAGE", "FESTA")
        }

        # Giorni molto pieni e molto vuoti
        giorni_pieni = [d for d, c in carichi.items() if c >= 5]
        giorni_vuoti = [d for d, c in carichi.items() if c <= 2]

        if not giorni_pieni or not giorni_vuoti:
            continue

        for data_piena in giorni_pieni:
            for data_vuota in giorni_vuoti:

                # NON toccare giorni speciali/fissi
                g_vuota = next(g for g in giorni if g["data"] == data_vuota)
                if g_vuota.get("speciale") or g_vuota.get("fisso") or g_vuota.get("tipo") in ("SPECIALE", "STAGE", "FESTA"):
                    continue

                # Regola di validità per il giorno vuoto
                if data_vuota < date(data_vuota.year, 3, 1):
                    def giornata_dest_valida():
                        ore_presenti = [h for h in range(ore_giornaliere) if griglia[data_vuota][h] is not None]
                        return len(ore_presenti) == ore_giornaliere
                else:
                    def giornata_dest_valida():
                        return giornata_valida(griglia, data_vuota, ore_giornaliere, g_vuota)

                for ora_dest in range(ore_giornaliere):

                    # NON piazzare sopra slot speciali
                    if griglia[data_vuota][ora_dest] and griglia[data_vuota][ora_dest].get("origine") == "speciale":
                        continue

                    if griglia[data_vuota][ora_dest] is not None:
                        continue

                    if occ.classe_occupata(classe.id, data_vuota, ora_dest):
                        continue

                    # Ora cerchiamo uno slot spostabile nel giorno pieno
                    for ora_src in range(ore_giornaliere):

                        slot = griglia[data_piena][ora_src]
                        if slot is None:
                            continue

                        # NON spostare slot speciali/fissi
                        if slot.get("origine") == "speciale" or slot.get("tipo") == "SPECIALE":
                            continue
                        if slot.get("fisso"):
                            continue
                        if slot.get("tipo") in ("STAGE", "FESTA", "PROFESSIONALE"):
                            continue
                        if slot.get("origine") in ("fisso",):
                            continue
                        if slot.get("docente") and "DOC EST" in slot.get("docente"):
                            continue

                        docente_id = slot.get("docente_id")
                        materia = slot.get("materia")

                        # Blocchi > 1 non spostabili
                        mid = next((m for m, info in materie_info.items() if info["nome"] == materia), None)
                        if mid:
                            blocco = materie_info[mid].get("blocco_orario", 1)
                            if blocco > 1:
                                continue

                        # Controllo slot destinazione
                        giorno_it_dest = g_vuota["giorno_it"]
                        if not slot_assegnabile(griglia, classe.id, docente_id, data_vuota, ora_dest, docente_ok, giorno_it_dest):
                            continue

                        # 🔥 Simulazione per verificare validità della giornata
                        griglia[data_vuota][ora_dest] = slot
                        griglia[data_piena][ora_src] = None

                        if not giornata_dest_valida():
                            # rollback
                            griglia[data_piena][ora_src] = slot
                            griglia[data_vuota][ora_dest] = None
                            continue

                        # rollback prima dello spostamento reale
                        griglia[data_piena][ora_src] = slot
                        griglia[data_vuota][ora_dest] = None

                        # 🔥 SPOSTAMENTO REALE
                        piazza_blocco(
                            griglia,
                            data_vuota,
                            ora_dest,
                            1,
                            slot["materia"],
                            slot["docente"],
                            docente_id,
                            None,
                            classe_id=classe.id,
                            materia_id=slot.get("materia_id"),
                            tipo="ORDINARIO",
                            origine="riequilibrio"
                        )

                        griglia[data_piena][ora_src] = None

                        if docente_id:
                            occ.libera(docente_id, data_piena, ora_src)
                            occ.occupa(docente_id, classe.id, data_vuota, ora_dest)

                        changed = True
                        break

                    if changed:
                        break
                if changed:
                    break
            if changed:
                break

    return changed


# ------------------------------------------------------------
# 7.5) BACKFILL — PATCHATO (INVARIATO)
# ------------------------------------------------------------
def backfill_buchi(griglie, settimane_classe, classe, materie_info, docente_ok):

    changed = False
    ore_giornaliere = classe.ore_massime_giornaliere or 6

    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
        griglia = griglie[key]

        for g in giorni:
            data = g["data"]
            giorno_it = g["giorno_it"]

            # 🔥 NON toccare giorni speciali, fissi, stage, festa
            if g.get("speciale") or g.get("fisso") or g.get("tipo") in ("SPECIALE", "STAGE", "FESTA"):
                continue

            # Regola di validità per il giorno corrente
            if data < date(data.year, 3, 1):
                def giornata_target_valida():
                    ore_presenti = [h for h in range(ore_giornaliere) if griglia[data][h] is not None]
                    return len(ore_presenti) == ore_giornaliere
            else:
                def giornata_target_valida():
                    return giornata_valida(griglia, data, ore_giornaliere, g)

            for ora in range(ore_giornaliere):

                # NON piazzare sopra slot speciali
                if griglia[data][ora] and griglia[data][ora].get("origine") == "speciale":
                    continue

                # Slot deve essere vuoto
                if griglia[data][ora] is not None:
                    continue

                # Classe libera
                if occ.classe_occupata(classe.id, data, ora):
                    continue

                # Cerchiamo nel futuro
                for future_key in sorted(settimane_classe.keys()):
                    if future_key <= key:
                        continue

                    future_giorni = sorted(
                        settimane_classe[future_key],
                        key=lambda x: x["data"]
                    )
                    future_griglia = griglie[future_key]

                    trovato = False

                    for fg in future_giorni:
                        f_data = fg["data"]

                        # NON toccare giorni speciali, fissi, stage, festa
                        if fg.get("speciale") or fg.get("fisso") or fg.get("tipo") in ("SPECIALE", "STAGE", "FESTA"):
                            continue

                        for f_ora in range(ore_giornaliere):

                            slot = future_griglia[f_data][f_ora]
                            if slot is None:
                                continue

                            # NON prendere slot speciali
                            if slot.get("origine") == "speciale" or slot.get("tipo") == "SPECIALE":
                                continue

                            # NON prendere fissi, professionali, doc est
                            if slot.get("fisso"):
                                continue
                            if slot.get("tipo") in ("STAGE", "FESTA", "PROFESSIONALE"):
                                continue
                            if slot.get("origine") in ("fisso",):
                                continue
                            if slot.get("docente") and "DOC EST" in slot.get("docente"):
                                continue

                            docente_id = slot.get("docente_id")

                            # Vincoli docente
                            if docente_id and not docente_ok(docente_id, data, giorno_it, ora, 1):
                                continue
                            if docente_id and not docente_disponibile_global(docente_id, data, ora):
                                continue

                            # Classe libera
                            if occ.classe_occupata(classe.id, data, ora):
                                continue

                            # 🔥 Simulazione per verificare validità della giornata
                            griglia[data][ora] = slot
                            future_griglia[f_data][f_ora] = None

                            if not giornata_target_valida():
                                # rollback
                                future_griglia[f_data][f_ora] = slot
                                griglia[data][ora] = None
                                continue

                            # rollback prima dello spostamento reale
                            future_griglia[f_data][f_ora] = slot
                            griglia[data][ora] = None

                            # 🔥 SPOSTAMENTO REALE
                            piazza_blocco(
                                griglia,
                                data,
                                ora,
                                1,
                                slot["materia"],
                                slot["docente"],
                                docente_id,
                                None,
                                classe_id=classe.id,
                                materia_id=slot.get("materia_id"),
                                tipo="ORDINARIO",
                                origine="backfill"
                            )

                            future_griglia[f_data][f_ora] = None
                            if docente_id:
                                occ.libera(docente_id, f_data, f_ora)
                                occ.occupa(docente_id, classe.id, data, ora)

                            trovato = True
                            changed = True
                            break

                        if trovato:
                            break
                    if trovato:
                        break

    return changed


# ------------------------------------------------------------
# 8) ORDINARIO GLOBALE COMPLETO
# ------------------------------------------------------------
from app.utils.fixed_days_handler import apply_fixed_days

def apply_ordinary(
    griglie,
    settimane_classe,
    classe,
    materie_info,
    materie_dict,
    docenti_dict,
    occupazione_docenti,
    docente_ok
):

    # 0) Inizializza OCCUPAZIONE_CLASSI_GLOBALE
    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
        for g in giorni:
            data = g["data"]
            occ.OCCUPAZIONE_CLASSI_GLOBALE.setdefault(classe.id, {})
            occ.OCCUPAZIONE_CLASSI_GLOBALE[classe.id].setdefault(data, set())

    # 0.5) Inizializza OCCUPAZIONE_DOCENTI_GLOBALE 
    inizializza_occupazione_globale_da_locale(occupazione_docenti)

    # 1) Giorni fissi
    giorni_fissi_classe = getattr(classe, "giorni_fissi", None)

    giorni_settimana = [
        g
        for settimana in settimane_classe.values()
        for g in settimana
    ]

    apply_fixed_days(
        griglia=griglie,
        giorni_settimana=giorni_settimana,
        classe=classe,
        materie_info=materie_info,
        materie_dict=materie_dict,
        occupazione_docenti=occupazione_docenti,
        giorni_fissi_classe=giorni_fissi_classe,
        docente_ok=docente_ok
    )

    # 2) Distribuzione iniziale
    distribuisci_fabbisogno(
        griglie,
        settimane_classe,
        classe,
        materie_info,
        docente_ok
    )

    

    # 3) Ciclo di ottimizzazione GLOBALE
    #    Fino a 100 passate, ma ci fermiamo prima se:
    #    - nessuna funzione cambia più nulla
    #    - tutte le giornate sono "legali" (almeno 4 ore consecutive dopo il 1 marzo)
    MAX_PASSATE = 100

    for _ in range(MAX_PASSATE):
        changed = False

        # 1) Garantisce 4 ore consecutive (dopo marzo)
        changed |= garantisci_quattro_ore_consecutive(
            griglie,
            settimane_classe,
            classe,
            materie_info,
            docente_ok
        )

        # 2) Compattazione aggressiva (riempie buchi prendendo dal futuro)
        changed |= compattazione_aggressiva(
            griglie,
            settimane_classe,
            classe,
            materie_info,
            docente_ok
        )

        # 3) Riequilibrio giornate (sposta da giorni pieni a vuoti)
        changed |= riequilibra_giornate(
            griglie,
            settimane_classe,
            classe,
            materie_info,
            docente_ok
        )

        # 4) Backfill (riempie buchi finali)
        changed |= backfill_buchi(
            griglie,
            settimane_classe,
            classe,
            materie_info,
            docente_ok
        )

        # Se nessuna funzione ha cambiato nulla → stop
        if not changed:
            break

        # Se tutte le giornate sono "legali" → stop
        if tutte_giornate_legali(griglie, settimane_classe, classe):
            break


        
    
    # 4.1) Compattazione finale
    compatta_settimane(griglie, settimane_classe)

    # 4.5) Se la classe ha finito tutte le ore → interrompi
    if classe_ha_finito(materie_info):
        return

    # 5) Recupero ore non piazzate
    recupera_debito_residuo(
        griglie,
        settimane_classe,
        classe,
        materie_info,
        docente_ok
    )

    # 5.5) Dopo il recupero, se la classe ha finito → interrompi
    if classe_ha_finito(materie_info):
        return

    
    
def recupera_debito_residuo(griglie, settimane_classe, classe, materie_info, docente_ok):

    changed = False
    ore_giornaliere = classe.ore_massime_giornaliere or 6

    for mid, info_m in materie_info.items():
        debito = info_m.get("debito_residuo", 0)
        if debito <= 0:
            continue

        docente_id = info_m.get("docente_id")
        docente_nome = info_m.get("docente_nome", "")
        blocco = info_m.get("blocco_orario", 1)

        for key in sorted(settimane_classe.keys()):
            giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
            griglia = griglie[key]

            for g in giorni:
                data = g["data"]
                giorno_it = g["giorno_it"]

                # Salta giorni speciali / STAGE / FESTA
                if g.get("speciale") or g.get("tipo") in ("STAGE", "FESTA"):
                    continue

                for ora in range(ore_giornaliere - (blocco - 1)):

                    if debito <= 0:
                        break

                    # Controllo blocco intero con slot_assegnabile
                    ok = True
                    for h in range(ora, ora + blocco):
                        if not slot_assegnabile(griglia, classe.id, docente_id, data, h, docente_ok, giorno_it):
                            ok = False
                            break
                    if not ok:
                        continue

                    # Evita buchi nella giornata
                    if crea_buco_in_giornata(griglia, data, ora, blocco):
                        continue

                    # --- PIAZZAMENTO ---
                    piazza_blocco(
                        griglia,
                        data,
                        ora,
                        blocco,
                        info_m["nome"],
                        docente_nome,
                        docente_id,
                        None,
                        classe_id=classe.id,
                        materia_id=mid,
                        tipo="RECUPERO",
                        origine="recupero"
                    )

                    # Aggiorna occupazione globale docente
                    if docente_id is not None:
                        for h in range(ora, ora + blocco):
                            occ.occupa(docente_id, classe.id, data, h)

                    info_m["debito_residuo"] -= blocco
                    info_m["ore_assegnate"] += blocco
                    debito -= blocco
                    changed = True

    return changed


# ------------------------------------------------------------
# 9) COMPATIBILITÀ LEGACY
# ------------------------------------------------------------
def registra_occupazione(*args, **kwargs):
    """
    Funzione di compatibilità per vecchi import.
    La logica di occupazione è gestita direttamente nelle funzioni sopra.
    """
    pass


def classe_ha_finito(materie_info):
    return all(info.get("debito_residuo", 0) <= 0 for info in materie_info.values())
