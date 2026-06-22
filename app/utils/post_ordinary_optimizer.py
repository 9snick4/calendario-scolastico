# app/utils/post_ordinary_optimizer.py

from copy import deepcopy
import app.utils.occupazione as occ


from datetime import datetime, date

def minimo_ore_giornata(data_g):
    """
    Prima del 1 marzo → minimo 6 ore
    Dal 1 marzo in poi → minimo 4 ore
    Accetta sia stringhe 'YYYY-MM-DD' che datetime.date.
    """

    # Se è già un datetime.date → ok
    if isinstance(data_g, date):
        data = data_g
    else:
        # Altrimenti è una stringa
        data = datetime.strptime(data_g, "%Y-%m-%d").date()

    cutoff = date(data.year, 3, 1)
    return 6 if data < cutoff else 4



############################################################
# UTILITY DI SICUREZZA VINCOLI
############################################################

def slot_spostabile(slot):
    """
    Uno slot è spostabile solo se NON è fisso, speciale, stage o festa.
    (Qui resta per compatibilità, ma nella versione safe non spostiamo più nulla.)
    """
    if not slot:
        return False
    if slot.get("fisso"):
        return False
    if slot.get("tipo") in ("SPECIALE", "STAGE", "FESTA"):
        return False
    return True


def docente_puo_stare(docente_ok, docente_disponibile_global, docente_id, data, giorno_it, ora):
    """Controlla tutti i vincoli docente (inclusa occupazione globale)."""
    if docente_ok and not docente_ok(docente_id, data, giorno_it, ora, 1):
        return False
    if not docente_disponibile_global(docente_id, data, ora):
        return False
    return True


def marca_occupato_globale(docente_id, data, ora):
    """
    Aggiorna l'occupazione globale del docente per evitare sovrapposizioni
    tra classi dopo le forzature post-ordinario.
    """
    d_doc = occ.OCCUPAZIONE_DOCENTI_GLOBALE.setdefault(docente_id, {})
    d_day = d_doc.setdefault(data, {})
    d_day[ora] = 1


############################################################
# 1) COMPATTATORE 2.0 (DISABILITATO NELLA VERSIONE SAFE)
############################################################

def compatta_giornata(row, data_g, giorno_it, docente_ok, docente_disponibile_global):
    """
    Compatta una giornata eliminando buchi, ma rispettando TUTTI i vincoli.
    Supporta sia lista che dict {ora: slot}.

    N.B.: nella versione SAFE del motore globale NON viene usata,
    per evitare di spostare ore senza poter aggiornare correttamente
    l'occupazione globale su tutte le classi.
    """
    # Normalizza: dict {ora: slot} → lista ordinata
    if isinstance(row, dict):
        ore_keys = sorted(row.keys())
        lista = [row[k] for k in ore_keys]
    else:
        ore_keys = list(range(len(row)))
        lista = list(row)

    ore = len(lista)
    nuova = lista[:]

    mobili = [(i, slot) for i, slot in enumerate(lista) if slot_spostabile(slot)]
    contenuto = [slot for _, slot in mobili]

    idx = 0
    for i in range(ore):
        if lista[i] and not slot_spostabile(lista[i]):
            nuova[i] = lista[i]
            continue

        if idx < len(contenuto):
            slot = contenuto[idx]
            docente_id = slot["docente_id"]

            if docente_puo_stare(docente_ok, docente_disponibile_global, docente_id, data_g, giorno_it, i):
                nuova[i] = slot
                idx += 1
            else:
                nuova[i] = None
        else:
            nuova[i] = None

    # Ritorna nel formato originale
    if isinstance(row, dict):
        return {k: nuova[i] for i, k in enumerate(ore_keys)}
    else:
        return nuova


############################################################
# 2) VALIDATORE ATTIVO VINCOLO-SAFE
############################################################

def _normalizza_row(row):
    """Ritorna (slots, ore_keys, is_dict) per gestire sia lista che dict."""
    if isinstance(row, dict):
        ore_keys = sorted(row.keys())
        slots = [row[k] for k in ore_keys]
        is_dict = True
    else:
        ore_keys = list(range(len(row)))
        slots = list(row)
        is_dict = False
    return slots, ore_keys, is_dict


def giornata_valida(row):
    """
    Regole:
    - se c'è STAGE/FESTA → sempre valido
    - se c'è uno slot SPECIALE o fisso → consideriamo la giornata valida e intoccabile
    - altrimenti: niente 0 ore, niente 2 ore, almeno 4 consecutive.
    """
    slots, _, _ = _normalizza_row(row)

    # Giorni con STAGE/FESTA → sempre validi
    if any(slot and slot.get("materia") in ("STAGE", "FESTA") for slot in slots):
        return True

    # Giorni con slot SPECIALE o fisso → li consideriamo validi e non li tocchiamo
    if any(slot and (slot.get("tipo") == "SPECIALE" or slot.get("fisso")) for slot in slots):
        return True

    ore = sum(1 for slot in slots if slot)
    if ore == 0 or ore == 2:
        return False

    consecutive = 0
    for slot in slots:
        if slot:
            consecutive += 1
            if consecutive >= 4:
                return True
        else:
            consecutive = 0

    return False


def forza_giornata_valida(row, materie_info, materie_dict, docenti_dict,
                          docente_ok, docente_disponibile_global, data_g, giorno_it):
    """
    Forza la giornata a diventare valida rispettando i vincoli docente
    e aggiornando l'occupazione globale.

    NON sposta slot esistenti, aggiunge solo nuove ore in buchi liberi.
    """
    slots, ore_keys, is_dict = _normalizza_row(row)

    # Se già valida (o speciale/fissa) non tocchiamo nulla
    if giornata_valida(slots):
        return row

    for mid, info in materie_info.items():
        if info["debito_residuo"] <= 0:
            continue

        docente_id = info["docente_id"]

        for i in range(len(slots)):
            if slots[i] is not None:
                continue

            # Rispetta vincoli docente + occupazione globale
            if not docente_puo_stare(docente_ok, docente_disponibile_global,
                                     docente_id, data_g, giorno_it, i):
                continue

            slots[i] = {
                "materia": materie_dict[mid],
                "docente": docenti_dict[docente_id],
                "docente_id": docente_id,
                "fisso": False,
                "tipo": "ORDINARIO",
                "origine": "forzato"
            }

            # Aggiorna debiti
            info["debito_residuo"] -= 1
            info["ore_assegnate"] += 1

            # Aggiorna occupazione globale per evitare conflitti con altre classi
            marca_occupato_globale(docente_id, data_g, i)

            # Se ora la giornata è valida, ci fermiamo
            if giornata_valida(slots):
                if is_dict:
                    return {k: slots[idx] for idx, k in enumerate(ore_keys)}
                else:
                    return slots

    # Ricostruisci nel formato originale anche se non siamo riusciti a renderla valida
    if is_dict:
        return {k: slots[idx] for idx, k in enumerate(ore_keys)}
    else:
        return slots


############################################################
# 3) RIEQUILIBRATORE SETTIMANALE (DISABILITATO NELLA VERSIONE SAFE)
############################################################

def riequilibra_settimana(griglia, giorni_settimana, docente_ok, docente_disponibile_global):
    """
    Riequilibra ore tra giorni rispettando i vincoli docente.

    N.B.: nella versione SAFE del motore globale NON viene usato nella
    funzione principale, per evitare spostamenti tra giorni che
    romperebbero l'occupazione globale.
    """
    # griglia: {data: {ora: slot} oppure data: [slot0, slot1, ...]}

    # Conta ore per giorno
    conteggi = {}
    for g in giorni_settimana:
        data = g["data"]
        row = griglia[data]
        if isinstance(row, dict):
            slots = list(row.values())
        else:
            slots = list(row)
        conteggi[data] = sum(1 for s in slots if s)

    media = sum(conteggi.values()) / len(conteggi)

    pieni = [d for d, ore in conteggi.items() if ore > media + 1]
    vuoti = [d for d, ore in conteggi.items() if ore < media - 1]

    for d_pieno in pieni:
        for d_vuoto in vuoti:
            row_p = griglia[d_pieno]
            row_v = griglia[d_vuoto]

            # Normalizza entrambe
            if isinstance(row_p, dict):
                keys_p = sorted(row_p.keys())
                slots_p = [row_p[k] for k in keys_p]
            else:
                keys_p = list(range(len(row_p)))
                slots_p = list(row_p)

            if isinstance(row_v, dict):
                keys_v = sorted(row_v.keys())
                slots_v = [row_v[k] for k in keys_v]
            else:
                keys_v = list(range(len(row_v)))
                slots_v = list(row_v)

            giorno_it_v = next(g["giorno_it"] for g in giorni_settimana if g["data"] == d_vuoto)

            for i, slot in enumerate(slots_p):
                if not slot_spostabile(slot):
                    continue

                docente_id = slot["docente_id"]

                for j in range(len(slots_v)):
                    if slots_v[j] is None:

                        if docente_puo_stare(docente_ok, docente_disponibile_global,
                                             docente_id, d_vuoto, giorno_it_v, j):
                            slots_v[j] = slot
                            slots_p[i] = None
                            break

            # Ricostruisci nel formato originale
            if isinstance(row_p, dict):
                griglia[d_pieno] = {k: slots_p[i] for i, k in enumerate(keys_p)}
            else:
                griglia[d_pieno] = slots_p

            if isinstance(row_v, dict):
                griglia[d_vuoto] = {k: slots_v[i] for i, k in enumerate(keys_v)}
            else:
                griglia[d_vuoto] = slots_v

    return griglia


############################################################
# 4) FUNZIONE PRINCIPALE (VERSIONE SAFE)
############################################################

def ottimizza_post_ordinario(
    griglie,
    settimane_classe,
    materie_info,
    materie_dict,
    docenti_dict,
    docente_ok,
    docente_disponibile_global,
    classe_id
):
    """
    Versione SAFE:
    - non sposta ore
    - non riequilibra settimane
    - aggiunge solo ore compatibili
    - ripete fino a 100 volte o fino a quando tutte le giornate sono valide
    """

    MAX_PASSATE = 100

    for _ in range(MAX_PASSATE):
        cambiato = False

        for key, giorni in settimane_classe.items():
            for g in giorni:
                data_g = g["data"]
                giorno_it = g["giorno_it"]
                row = griglie[key][data_g]

                # Normalizza
                slots, ore_keys, is_dict = _normalizza_row(row)

                # Se contiene speciali/fissi → non si tocca
                if any(s and (s.get("tipo") in ("SPECIALE", "STAGE", "FESTA") or s.get("fisso")) for s in slots):
                    continue

                # Calcola minimo richiesto
                minimo = minimo_ore_giornata(data_g)

                ore_presenti = sum(1 for s in slots if s)

                if ore_presenti >= minimo:
                    continue  # già ok

                # Prova ad aggiungere ore finché non raggiunge il minimo
                before = ore_presenti
                row2 = forza_giornata_valida(
                    row,
                    materie_info,
                    materie_dict,
                    docenti_dict,
                    docente_ok,
                    docente_disponibile_global,
                    data_g,
                    giorno_it
                )

                # Ricalcola ore
                slots2, _, _ = _normalizza_row(row2)
                after = sum(1 for s in slots2 if s)

                if after > before:
                    cambiato = True

                griglie[key][data_g] = row2

        if not cambiato:
            break  # tutto stabile → stop

    return griglie
