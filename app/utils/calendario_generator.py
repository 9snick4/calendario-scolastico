# app/utils/calendario_generator.py

from app.utils.festivita_handler import apply_festivita

from .class_setup import prepara_classi
from .fixed_days_handler import apply_fixed_days
from .special_days_handler import apply_special_days
from .stage_handler import apply_stage

# ============================================================
# COSTANTI ANTI-LOOP
# ============================================================
MAX_ITER = 5


import app.utils.occupazione as occ
from app.utils.orario_utils import (
    costruisci_settimana,
    crea_griglia_settimanale,
    salva_calendari,
)
from app.utils.ordinary_placement import ordinary_placement, prepara_classi_data
from app.utils.utils_scheduler import (
    docente_ok_wrapper,
)

print(">>> VERSIONE PATCHATA DEFINITIVA")


def _slot_intoccabile(cd, data_g, h):
    """
    Versione del calendario_generator di _slot_intoccabile.

    Restituisce True se lo slot non deve essere toccato dai ribilanciamenti
    (fasi 5-8). Controlla: fissi_per_giorno, speciali_per_giorno e il tipo
    del giorno (STAGE, FESTA, SPECIALE).
    """
    # slot marcato come fisso o speciale
    if (data_g, h) in cd.get("fissi_per_giorno", set()):
        return True
    if (data_g, h) in cd.get("speciali_per_giorno", set()):
        return True

    # tipo giorno bloccante
    tipo_giorno = cd.get("tipo_giorno", {})
    tg = tipo_giorno.get(data_g)
    return tg in ("STAGE", "FESTA", "SPECIALE")


def _rispetta_ore_minime_consecutive(row, h, materia_id, ore_minime, ore_g):
    """
    Controlla se piazzare 1 ora nello slot h puo' far parte di un blocco
    di almeno ore_minime ore consecutive per quella materia.

    Versione semplificata: lo slot h e' valido se almeno uno dei vicini
    (h-1 o h+1) contiene gia' la stessa materia.

    CORNER CASE: se ore_minime <= 1 restituisce sempre True.
    CORNER CASE: ore singole isolate rifiutate quando ore_minime > 1,
    per non spezzare il vincolo di blocco della materia.
    """

    if ore_minime <= 1:
        return True

    same_before = (
        h - 1 >= 0
        and isinstance(row[h - 1], dict)
        and row[h - 1].get("materia_id") == materia_id
    )
    same_after = (
        h + 1 < ore_g
        and isinstance(row[h + 1], dict)
        and row[h + 1].get("materia_id") == materia_id
    )

    return not (not same_before and not same_after)


def fallback_riempimento_buchi(cd, docente_ok_wrapper):
    """
    Fase 5 del ciclo di ribilanciamento: riempie gli slot vuoti rimasti.

    Funziona DOPO il motore ordinario, quando rimangono ore di debito e
    ancora buchi disponibili. Scansiona tutti gli slot liberi, li ordina
    per data discendente (priorita' alle date piu' lontane), e per ogni
    materia con debito cerca di piazzare le ore mancanti.

    Vincoli rispettati:
    - Slot non intoccabile
    - Docente disponibile (globale + orario)
    - Rispetta ore_minime_consecutive

    Restituisce il numero di ore piazzate in questa passata.
    """

    cambiamenti = 0

    materie = cd["materie_attive"]
    griglie = cd["griglie"]
    giorni_per_key = cd["giorni_per_key"]
    ore_g = cd["ore_g"]
    classe_id = cd["classe"].id

    slot_liberi = []

    for key, giorni in giorni_per_key.items():
        griglia = griglie[key]
        for g in giorni:
            data_g = g["data"]
            row = griglia[data_g]
            for h in range(ore_g):
                if row[h] is None and not _slot_intoccabile(cd, data_g, h):
                    slot_liberi.append((data_g, key, h, row))

    slot_liberi.sort(key=lambda x: (x[0], x[2]), reverse=True)

    materie_con_debito = [
        (mid, info)
        for mid, info in materie.items()
        if info.get("debito_residuo", 0) > 0
    ]

    for mid, info in materie_con_debito:
        debito = info.get("debito_residuo", 0)
        if debito <= 0:
            continue

        docente_id = info.get("docente_id")
        ore_minime = info.get("ore_minime_consecutive", 1)
        nome_materia = info.get("nome", f"Materia {mid}")

        for data_g, key, h, row in slot_liberi:
            if debito <= 0:
                break

            if row[h] is not None:
                continue

            giorno_it = None
            for g in giorni_per_key[key]:
                if g["data"] == data_g:
                    giorno_it = g["giorno_it"]
                    break

            if not docente_ok_wrapper(docente_id, data_g, h, giorno_it, 1):
                continue
            if not occ.docente_libero(docente_id, data_g, h):
                continue

            if not _rispetta_ore_minime_consecutive(row, h, mid, ore_minime, ore_g):
                continue

            # piazza ora
            row[h] = {
                "materia_id": mid,
                "materia": nome_materia,
                "docente_id": docente_id,
                "origine": "critica",
                "locked": True,
            }

            occ.occupa(docente_id, classe_id, data_g, h)

            info["ore_assegnate"] += 1
            info["debito_residuo"] -= 1
            debito -= 1
            cambiamenti += 1

    return cambiamenti




def fase6_ribilanciamento(cd, docente_ok_wrapper):
    """
    Fase 6: ribilanciamento intra-classe.

    Libera slot per materie critiche (debito > 0) spostando blocchi di
    materie leggere (debito=0, ore_minime=1) in altri slot della stessa
    classe.

    Per ogni materia critica cerca uno slot occupato da una materia
    spostabile, trova una destinazione libera per quel blocco, lo sposta,
    aggiorna l'occupazione globale e piazza l'ora critica.

    Non tocca slot con origine fisso/speciale/fase6/fase7/critica
    e non tocca slot locked.

    Restituisce il numero di cambiamenti effettuati.
    """

    cambiamenti = 0

    materie = cd["materie_attive"]
    griglie = cd["griglie"]
    giorni_per_key = cd["giorni_per_key"]
    ore_g = cd["ore_g"]
    classe_id = cd["classe"].id

    # 1) Materie critiche (con debito)
    materie_con_debito = [
        (mid, info)
        for mid, info in materie.items()
        if info.get("debito_residuo", 0) > 0
    ]
    if not materie_con_debito:
        return 0

    # 2) Materie spostabili (non critiche)
    materie_spostabili = {
        mid: info
        for mid, info in materie.items()
        if info.get("debito_residuo", 0) == 0
        and info.get("ore_minime_consecutive", 1) == 1
    }

    # 3) Trova blocco consecutivo
    def trova_blocco(row, h, mid):
        start = h
        end = h
        while (
            start > 0
            and isinstance(row[start - 1], dict)
            and row[start - 1].get("materia_id") == mid
        ):
            start -= 1
        while (
            end + 1 < ore_g
            and isinstance(row[end + 1], dict)
            and row[end + 1].get("materia_id") == mid
        ):
            end += 1
        return start, end

    # 4) Per ogni materia critica
    for mid_critica, info_critica in materie_con_debito:
        docente_critico = info_critica["docente_id"]
        nome_critica = info_critica["nome"]
        debito = info_critica["debito_residuo"]

        for key, giorni in giorni_per_key.items():
            griglia = griglie[key]

            for g in giorni:
                data_g = g["data"]
                giorno_it = g["giorno_it"]
                row = griglia[data_g]

                for h in range(ore_g):

                    if debito <= 0:
                        break

                    # docente critico deve essere libero e disponibile
                    if not docente_ok_wrapper(docente_critico, data_g, h, giorno_it, 1):
                        continue
                    if not occ.docente_libero(docente_critico, data_g, h):
                        continue

                    # slot occupato → tentiamo spostamento
                    if row[h] is None:
                        continue

                    slot = row[h]

                    # NON toccare fissi/speciali/locked/fase6/fase7/critica
                    if slot.get("origine") in ("fisso", "speciale", "fase6", "fase7", "critica"):
                        continue
                    if slot.get("locked"):
                        continue

                    mid_spostabile = slot.get("materia_id")
                    if mid_spostabile not in materie_spostabili:
                        continue

                    docente_spostabile = slot.get("docente_id")

                    # trova blocco
                    start, end = trova_blocco(row, h, mid_spostabile)
                    blocco_len = end - start + 1

                    # 5) cerca destinazione per il blocco
                    trovato = False
                    for key2, giorni2 in giorni_per_key.items():
                        if trovato:
                            break

                        griglia2 = griglie[key2]

                        for g2 in giorni2:
                            if trovato:
                                break

                            data2 = g2["data"]
                            giorno2 = g2["giorno_it"]
                            row2 = griglia2[data2]

                            for h2 in range(ore_g - blocco_len + 1):

                                # destinazione deve essere libera
                                if any(row2[h2 + k] is not None for k in range(blocco_len)):
                                    continue

                                # NON piazzare in fissi/speciali
                                invalid_dest = False
                                for k in range(blocco_len):
                                    if (data2, h2 + k) in cd["fissi_per_giorno"]:
                                        invalid_dest = True
                                        break
                                    if (data2, h2 + k) in cd["speciali_per_giorno"]:
                                        invalid_dest = True
                                        break
                                if invalid_dest:
                                    continue

                                # docente spostabile deve essere libero e disponibile
                                if not all(
                                    docente_ok_wrapper(docente_spostabile, data2, h2 + k, giorno2, 1)
                                    and occ.docente_libero(docente_spostabile, data2, h2 + k)
                                    for k in range(blocco_len)
                                ):
                                    continue

                                # 🔥 1) libera occupazione originale del blocco
                                for k in range(blocco_len):
                                    occ.libera(docente_spostabile, data_g, start + k)

                                # 🔥 2) sposta blocco
                                blocco = row[start : end + 1]
                                for k in range(blocco_len):
                                    row2[h2 + k] = blocco[k]
                                    row2[h2 + k]["locked"] = True
                                    row[start + k] = None
                                    occ.occupa(docente_spostabile, classe_id, data2, h2 + k)

                                # 🔥 3) libera eventuale occupazione del docente critico
                                occ.libera(docente_critico, data_g, h)

                                # 🔥 4) piazza ora critica
                                row[h] = {
                                    "materia_id": mid_critica,
                                    "materia": nome_critica,
                                    "docente_id": docente_critico,
                                    "origine": "critica",
                                    "locked": True,
                                }
                                occ.occupa(docente_critico, classe_id, data_g, h)

                                # aggiorna contatori
                                info_critica["ore_assegnate"] += 1
                                info_critica["debito_residuo"] -= 1
                                debito -= 1
                                cambiamenti += 1

                                trovato = True
                                break

                if debito <= 0:
                    break
            if debito <= 0:
                break

    return cambiamenti

def fase7_ribilanciamento_interclassi(classi_data, docente_ok_wrapper):
    """
    Fase 7: ribilanciamento inter-classi (docente-centrico).

    Quando un docente insegna in piu' classi e una di esse ha ancora
    debito, tenta di liberare un'ora in un'altra classe (senza debito)
    per cederla alla classe critica.

    Costruisce una mappa docente -> classi, separa le materie con/senza
    debito, poi per ogni slot libero nella classe critica cerca un'ora
    spostabile in un'altra classe dello stesso docente.

    CORNER CASE: docente con una sola classe viene saltato.
    CORNER CASE: non tocca slot locked o di origine fase6/fase7/critica.

    Restituisce il numero di cambiamenti effettuati.
    """

    cambiamenti = 0

    # Mappa docente → classi in cui insegna
    doc_to_classi = {}
    for cd in classi_data:
        for _, info in cd["materie_attive"].items():
            docente_id = info.get("docente_id")
            if docente_id:
                doc_to_classi.setdefault(docente_id, set()).add(cd["classe"].id)

    # Per ogni docente che insegna in più classi
    for docente_id, classi_ids in doc_to_classi.items():
        if len(classi_ids) <= 1:
            continue

        # cd relativi a questo docente
        cd_doc = [cd for cd in classi_data if cd["classe"].id in classi_ids]

        # separa materie con debito e senza debito
        materie_con_debito = []
        materie_senza_debito = []

        for cd in cd_doc:
            for mid, info in cd["materie_attive"].items():
                if info.get("docente_id") != docente_id:
                    continue
                if info.get("debito_residuo", 0) > 0:
                    materie_con_debito.append((cd, mid, info))
                else:
                    materie_senza_debito.append((cd, mid, info))

        if not materie_con_debito or not materie_senza_debito:
            continue

        # Per ogni materia critica
        for cd_critica, mid_critica, info_critica in materie_con_debito:
            debito = info_critica["debito_residuo"]
            if debito <= 0:
                continue

            nome_critica = info_critica["nome"]
            giorni_per_key = cd_critica["giorni_per_key"]
            griglie_critica = cd_critica["griglie"]
            ore_g = cd_critica["ore_g"]
            classe_id_critica = cd_critica["classe"].id

            # Scansiona tutti gli slot della classe con debito
            for key, giorni in giorni_per_key.items():
                griglia = griglie_critica[key]

                for g in giorni:
                    data_g = g["data"]
                    giorno_it = g["giorno_it"]
                    row = griglia[data_g]

                    for h in range(ore_g):

                        if debito <= 0:
                            break

                        # docente deve essere libero e disponibile
                        if not docente_ok_wrapper(docente_id, data_g, h, giorno_it, 1):
                            continue
                        if not occ.docente_libero(docente_id, data_g, h):
                            continue

                        # slot deve essere libero
                        if row[h] is not None:
                            continue

                        # tenta di spostare un'ora da una classe senza debito
                        spostato = False

                        for cd_sorgente, mid_sorg, _info_sorg in materie_senza_debito:
                            if spostato:
                                break

                            griglie_sorg = cd_sorgente["griglie"]
                            giorni_sorg = cd_sorgente["giorni_per_key"]
                            ore_g_sorg = cd_sorgente["ore_g"]

                            for key2, giorni2 in giorni_sorg.items():
                                if spostato:
                                    break

                                griglia2 = griglie_sorg[key2]

                                for g2 in giorni2:
                                    if spostato:
                                        break

                                    data2 = g2["data"]
                                    giorno2 = g2["giorno_it"]
                                    row2 = griglia2[data2]

                                    for h2 in range(ore_g_sorg):
                                        if spostato:
                                            break

                                        slot2 = row2[h2]
                                        if not isinstance(slot2, dict):
                                            continue

                                        # NON toccare fissi/speciali/fase6/fase7/critica/locked
                                        if slot2.get("origine") in ("fisso", "speciale", "fase6", "fase7", "critica"):
                                            continue
                                        if slot2.get("locked"):
                                            continue

                                        # deve essere la materia sorgente
                                        if slot2.get("materia_id") != mid_sorg:
                                            continue

                                        # docente deve essere disponibile nello slot sorgente
                                        if not docente_ok_wrapper(docente_id, data2, h2, giorno2, 1):
                                            continue

                                        # 🔥 sposta ORA
                                        row[h] = {
                                            "materia_id": mid_critica,
                                            "materia": nome_critica,
                                            "docente_id": docente_id,
                                            "origine": "critica",
                                            "locked": True,
                                        }
                                        occ.occupa(docente_id, classe_id_critica, data_g, h)

                                        # libera sorgente
                                        row2[h2] = None
                                        occ.libera(docente_id, data2, h2)

                                        # aggiorna contatori
                                        info_critica["ore_assegnate"] += 1
                                        info_critica["debito_residuo"] -= 1
                                        debito -= 1
                                        cambiamenti += 1

                                        spostato = True
                                        break

                    if debito <= 0:
                        break
                if debito <= 0:
                    break

    return cambiamenti

def fase8_compattezza(cd, docente_ok_wrapper):
    """
    Fase 8: compattazione intra-classe.

    Riduce i buchi interni spostandoli verso l'inizio della giornata:
    per ogni buco (slot None) trova la prima lezione successiva non locked
    e la sposta in alto.

    Questo migliora la leggibilita' del calendario evitando orari "a buchi".

    CORNER CASE: non sposta slot locked o di origine fase6/fase7/critica.
    CORNER CASE: verifica la disponibilita' del docente nel nuovo slot.

    Restituisce il numero di cambiamenti effettuati.
    """

    cambiamenti = 0

    griglie = cd["griglie"]
    giorni_per_key = cd["giorni_per_key"]
    ore_g = cd["ore_g"]
    classe_id = cd["classe"].id

    for key, giorni in giorni_per_key.items():
        griglia = griglie[key]

        for g in giorni:
            data_g = g["data"]
            giorno_it = g["giorno_it"]
            row = griglia[data_g]

            # cerca buchi interni
            for h in range(ore_g - 1):

                if row[h] is not None:
                    continue  # non è un buco

                # cerca una lezione dopo
                for h2 in range(h + 1, ore_g):
                    slot2 = row[h2]
                    if not isinstance(slot2, dict):
                        continue

                    # NON toccare fissi/speciali/fase6/fase7/critica/locked
                    if slot2.get("origine") in ("fisso", "speciale", "fase6", "fase7", "critica"):
                        continue
                    if slot2.get("locked"):
                        continue

                    docente_id = slot2.get("docente_id")
                    if not docente_id:
                        continue

                    # docente deve essere libero nello slot più alto
                    if not docente_ok_wrapper(docente_id, data_g, h, giorno_it, 1):
                        continue
                    if not occ.docente_libero(docente_id, data_g, h):
                        continue

                    # 🔥 sposta verso l'alto
                    row[h] = slot2
                    row[h2] = None

                    occ.libera(docente_id, data_g, h2)
                    occ.occupa(docente_id, classe_id, data_g, h)

                    cambiamenti += 1
                    break  # passa al prossimo buco

    return cambiamenti

def genera_calendario_annuale():
    """
    Funzione principale dell'applicazione: genera il calendario scolastico
    annuale per tutte le classi.

    Pipeline completa:
    1. Reset delle occupazioni globali.
    2. prepara_classi() — carica DB e costruisce strutture dati per ogni classe.
    3. Per ogni classe, crea le griglie settimanali vuote.
    4. Per ogni settimana, applica in ordine:
       a. apply_stage         — blocca i giorni di stage
       b. apply_festivita     — blocca i giorni festivi
       c. apply_special_days  — piazza i giorni speciali
       d. apply_fixed_days    — piazza i giorni fissi
    5. piazzamento_ordinario() — motore a 8 fasi per il resto delle ore.
    6. costruisci_settimana() — converte le griglie nel calendario finale.
    7. salva_calendari() — assembla il dizionario da restituire.
    8. valida_motore() — verifica coerenza interna e stampa errori.

    Ritorna: dict {classe_id: {nome_classe, ore_giornaliere, calendario}}

    CORNER CASE: se griglie[key] e' None per una classe, quella settimana
    viene saltata con un avviso WARN (non genera eccezione).
    CORNER CASE: il ciclo di ribilanciamento (fasi 5-8) gira al massimo
    MAX_ITER volte; se nessuna fase produce cambiamenti si ferma prima.
    """

    occ.OCCUPAZIONE_DOCENTI_GLOBALE.clear()
    occ.OCCUPAZIONE_CLASSI_GLOBALE.clear()

    (
        classi_info,
        classi,
        materie_dict,
        docenti_dict,
        nomi_non_prof,
        occupazione_docenti,
    ) = prepara_classi()

    tutte_le_griglie = {}
    tutte_le_settimane = {}
    ore_giornaliere_max = 0

    for cid, info in classi_info.items():

        classe = info["classe"]
        settimane_classe = info["settimane_classe"]
        ore_giornaliere = info["ore_giornaliere"]
        materie_info = info["materie_info"]
        giorni_fissi_classe = info["giorni_fissi"]

        ore_giornaliere_max = max(ore_giornaliere_max, ore_giornaliere)

        calendario = []
        info["calendario"] = calendario

        griglie = {}
        for key in sorted(settimane_classe.keys()):
            giorni_settimana = sorted(
                settimane_classe[key], key=lambda x: x["data"]
            )
            griglie[key] = crea_griglia_settimanale(
                giorni_settimana, ore_giornaliere
            )

        for key in sorted(settimane_classe.keys()):
            giorni_settimana = sorted(
                settimane_classe[key], key=lambda x: x["data"]
            )

            apply_stage(griglie[key], giorni_settimana, classe)
            apply_festivita(griglie[key], giorni_settimana)

            apply_special_days(
                griglie[key],
                giorni_settimana,
                classe,
                materie_info,
                materie_dict,
                occupazione_docenti,
                docente_ok_wrapper,
            )

            apply_fixed_days(
                griglie[key],
                giorni_settimana,
                classe,
                materie_info,
                materie_dict,
                occupazione_docenti,
                giorni_fissi_classe,
                docente_ok_wrapper,
            )

        info["griglie"] = griglie
        tutte_le_griglie[cid] = griglie
        tutte_le_settimane[cid] = settimane_classe

    def piazzamento_ordinario(classi_info, docente_ok_wrapper):
        classi_data = prepara_classi_data(classi_info)

        # =========================
        # PRE-SETUP PER OGNI CLASSE
        # =========================
        for cd in classi_data:

            # tipo_giorno, settimane, settimana_per_data
            if (
                "tipo_giorno" not in cd
                or "settimane" not in cd
                or "settimana_per_data" not in cd
            ):
                tipo_giorno = {}
                settimane = {}
                settimana_per_data = {}

                for key, giorni in cd["settimane_classe"].items():
                    settimane[key] = [g["data"] for g in giorni]
                    for g in giorni:
                        data_g = g["data"]
                        tg = g.get("tipo_giorno") or g.get("tipo") or None
                        tipo_giorno[data_g] = tg
                        settimana_per_data[data_g] = key

                cd["tipo_giorno"] = tipo_giorno
                cd["settimane"] = settimane
                cd["settimana_per_data"] = settimana_per_data

            # fissi_per_giorno / speciali_per_giorno
            fissi_per_giorno = set()
            speciali_per_giorno = set()

            for key, giorni in cd["giorni_per_key"].items():
                griglia = cd["griglie"][key]
                for g in giorni:
                    data_g = g["data"]
                    row = griglia[data_g]
                    for h, slot in enumerate(row):
                        if isinstance(slot, dict):
                            origine = slot.get("origine")
                            if origine == "fisso":
                                fissi_per_giorno.add((data_g, h))
                            if origine == "speciale":
                                speciali_per_giorno.add((data_g, h))

            cd["fissi_per_giorno"] = fissi_per_giorno
            cd["speciali_per_giorno"] = speciali_per_giorno

            # salvo lo stato "libero_originale"
            cd["libero_originale"] = dict(cd["libero"])

            # motore ordinario
            ordinary_placement(cd, docente_ok_wrapper)

        # =========================
        # CICLO DI RIBILANCIAMENTO
        # =========================
        for _ in range(MAX_ITER):
            cambiamenti = 0

            # fasi intra-classe (per ogni cd)
            for cd in classi_data:
                cambiamenti += fallback_riempimento_buchi(cd, docente_ok_wrapper)
                cambiamenti += fase6_ribilanciamento(cd, docente_ok_wrapper)
                cambiamenti += fase8_compattezza(cd, docente_ok_wrapper)

            # fase inter-classi (docente-centrica)
            cambiamenti += fase7_ribilanciamento_interclassi(classi_data, docente_ok_wrapper)

            # se nessuna fase ha fatto cambiamenti → motore stabile, esco
            if cambiamenti == 0:
                break

        # =========================
        # DIAGNOSTICA
        # =========================
        from app.utils.diagnostica import diagnostica_classe, diagnostica_globale

        for cd in classi_data:
            if cd["classe"].nome_classe.strip().upper() == "3 A":
                diagnostica_classe(cd, docente_ok_wrapper)

        diagnostica_globale(classi_data, docente_ok_wrapper)



    piazzamento_ordinario(classi_info, docente_ok_wrapper)

    for _, info in classi_info.items():
        classe = info["classe"]
        settimane_classe = info["settimane_classe"]
        ore_giornaliere = info["ore_giornaliere"]
        calendario = info["calendario"]
        griglie = info["griglie"]

        for key in sorted(settimane_classe.keys()):
            if key not in griglie or griglie[key] is None:
                print(
                    f"[WARN] griglie[{key}] è None per la classe {classe.nome_classe}, salto costruisci_settimana."
                )
                continue

            giorni_settimana = sorted(
                settimane_classe[key], key=lambda x: x["data"]
            )
            costruisci_settimana(
                griglie[key],
                giorni_settimana,
                ore_giornaliere,
                calendario,
            )

    calendario_per_classe = salva_calendari(classi_info)

    from app.utils.validator import set_validator_cache, valida_motore

    set_validator_cache(calendario_per_classe, classi_info)

    errori = []
    for _, info in classi_info.items():
        griglie_classe = info.get("griglie")
        settimane_classe = info["settimane_classe"]
        ore_giornaliere = info["ore_giornaliere"]

        if not griglie_classe:
            continue

        err_classe = valida_motore(
            griglie_classe,
            settimane_classe,
            ore_giornaliere,
        )
        nome = info["classe"].nome_classe
        errori.extend([f"[{nome}] {e}" for e in err_classe])

    if errori:
        print("\n=== ERRORI TROVATI ===")
        for e in errori:
            print(e)
    else:
        print("\n=== TUTTO COERENTE ===")

    return calendario_per_classe
