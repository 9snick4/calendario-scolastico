# ============================================================
#   ORDINARY PLACEMENT -- VERSIONE DEFINITIVA PATCHATA
#   Protezione giorni speciali + giorni fissi + anti‑buco
# ============================================================

import app.utils.occupazione as occ
from app.utils.orario_utils import piazza_blocco


def prepara_classi_data(classi_info):
    """
    Converte classi_info (dizionario prodotto da prepara_classi) in una
    lista di strutture cd (class_data) utilizzate dal motore ordinario.

    Ogni cd contiene:
    - griglie           : dict settimana -> griglia settimanale
    - materie_attive    : dict materia_id -> info materia
    - libero            : dict (data, h) -> bool
    - giorni_per_key    : dict settimana -> lista giorni
    - settimane_classe  : struttura originale
    - tipo_giorno       : dict data -> tipo ("STAGE","FESTA","SPECIALE",None)
    - settimane         : dict settimana -> lista date
    - settimana_per_data: dict data -> chiave settimana
    - classe            : oggetto Classe
    - ore_g             : numero massimo di ore giornaliere
    """

    classi_data = []

    for _, info in classi_info.items():
        cd = {}

        cd["classe"] = info["classe"]
        cd["griglie"] = info["griglie"]
        cd["materie_attive"] = info["materie_info"]
        cd["settimane_classe"] = info["settimane_classe"]
        cd["ore_g"] = info["ore_giornaliere"]

        # Costruisci giorni_per_key
        giorni_per_key = {}
        for key, giorni in info["settimane_classe"].items():
            giorni_per_key[key] = [
                {
                    "data": g["data"],
                    "giorno_it": g["giorno_it"],
                    "tipo_giorno": g.get("tipo_giorno") or g.get("tipo")
                }
                for g in giorni
            ]
        cd["giorni_per_key"] = giorni_per_key

        # Costruisci tipo_giorno, settimane, settimana_per_data
        tipo_giorno = {}
        settimane = {}
        settimana_per_data = {}

        for key, giorni in giorni_per_key.items():
            settimane[key] = [g["data"] for g in giorni]
            for g in giorni:
                data_g = g["data"]
                tipo_giorno[data_g] = g.get("tipo_giorno")
                settimana_per_data[data_g] = key

        cd["tipo_giorno"] = tipo_giorno
        cd["settimane"] = settimane
        cd["settimana_per_data"] = settimana_per_data

        # Costruisci mappa libero: (data, h) → True/False
        libero = {}
        for key, giorni in giorni_per_key.items():
            griglia = cd["griglie"][key]
            for g in giorni:
                data_g = g["data"]
                row = griglia[data_g]
                for h, slot in enumerate(row):
                    libero[(data_g, h)] = (slot is None)

        cd["libero"] = libero

        classi_data.append(cd)

    return classi_data



def ordinary_placement(cd, docente_ok_wrapper):
    """
    Punto di ingresso del motore ordinario per una singola classe.

    Esegue in sequenza:
    1. fase1_calcolo_ore_settimanali  -- quante ore/settimana per materia
    2. fase2_piazzamento_forte        -- blocchi interi con vincolo ore_minime
    3. fase3_riempimento_soft         -- ore residue slot per slot
    4. fase4_riempimento_ultrasoft    -- secondo tentativo soft senza limiti blocco
    5. report_classe                  -- stampa statistica finale
    """
    fase1_calcolo_ore_settimanali(cd)
    fase2_piazzamento_forte(cd, docente_ok_wrapper)
    fase3_riempimento_soft(cd, docente_ok_wrapper)
    fase4_riempimento_ultrasoft(cd, docente_ok_wrapper)
    report_classe(cd)


# ============================================================
#   FASE 1 -- CALCOLO ORE SETTIMANALI
# ============================================================

def fase1_calcolo_ore_settimanali(cd):
    """
    Calcola la quota settimanale teorica di ogni materia.

    Formula: ore_settimanali = max(1, round(ore_annuali / num_settimane)).
    Le materie con ore_annuali < 30 ottengono 1 ora/settimana.
    Salva anche il valore _blocchi_minimi (= ore_minime_consecutive).
    """
    settimane = len(cd.get("settimane", {}))

    for _, info in cd["materie_attive"].items():
        ore_annuali = info.get("ore_annuali", 0)

        if ore_annuali < 30:
            info["ore_settimanali"] = 1
        else:
            info["ore_settimanali"] = max(1, round(ore_annuali / max(1, settimane)))

        info["_blocchi_minimi"] = info.get("ore_minime_consecutive", 1)


# ============================================================
#   FASE 2 -- PIAZZAMENTO FORTE
# ============================================================

def fase2_piazzamento_forte(cd, docente_ok_wrapper):
    """
    Prima fase di piazzamento: tenta di mettere blocchi INTERI per ogni
    materia, settimana per settimana.

    Le materie vengono ordinate per priorita' decrescente:
    ore/settimana -> blocchi_minimi -> ore_annuali.
    Per ogni settimana, per ogni materia, chiama _piazza_blocchi_settimanali.
    """
    materie = cd["materie_attive"]

    materie_ordinate = sorted(
        materie.items(),
        key=lambda kv: (
            -kv[1]["ore_settimanali"],
            -kv[1]["_blocchi_minimi"],
            -kv[1].get("ore_annuali", 0)
        )
    )

    for settimana in cd.get("settimane", {}):
        for mid, info in materie_ordinate:
            _piazza_blocchi_settimanali(cd, docente_ok_wrapper, mid, info, settimana)


# ============================================================
#   FUNZIONE OPERATIVA -- PIAZZAMENTO BLOCCHI
# ============================================================

def _slot_intoccabile(cd, data_g, h):
    """
    Restituisce True se lo slot (data_g, h) non puo' essere modificato.

    Uno slot e' intoccabile se:
    - non era libero nello stato originale (libero_originale)
    - il tipo giorno e' STAGE, FESTA o SPECIALE
    - lo slot e' nella lista dei fissi (fissi_per_giorno)
    - lo slot e' nella lista degli speciali (speciali_per_giorno)
    """
    # slot non libero
    if not cd["libero_originale"].get((data_g, h), False):
        return True

    # giorno speciale
    if cd["tipo_giorno"].get(data_g) in ("STAGE", "FESTA", "SPECIALE"):
        return True

    # slot fisso
    if (data_g, h) in cd.get("fissi_per_giorno", set()):
        return True

    # slot speciale
    return (data_g, h) in cd.get("speciali_per_giorno", set())


def _piazza_blocchi_settimanali(cd, docente_ok_wrapper, mid, info, settimana):
    """
    Tenta di piazzare la quota settimanale di una materia in una settimana.

    Logica:
    1. Calcola quante ore mancano (debito_residuo vs ore_da_piazzare).
    2. Piazza prima i blocchi interi di n ore consecutive (forte).
    3. Se rimane un resto, chiama _piazza_soft per l'ora singola.

    Selezione candidati (blocchi interi):
    - score penalizza la posizione centrale della giornata.
    - score penalizza la creazione di buchi interni.
    - score premia la compattazione con lezioni adiacenti.
    - Non piazza se il docente supera 3 ore nella stessa giornata.

    CORNER CASE: se nessun candidato e' disponibile in tutta la settimana,
    esce senza piazzare (le ore rimangono nel debito_residuo).
    """
    ore_sett = info["ore_settimanali"]
    n        = info["_blocchi_minimi"]
    docente_id   = info.get("docente_id")
    docente_nome = info.get("docente_nome", "")
    nome_materia = info["nome"]

    # quante ore già piazzate in questa settimana?
    ore_reali = 0
    for _, griglia in cd["griglie"].items():
        for data_g in cd["settimane"][settimana]:
            if data_g in griglia:
                for slot in griglia[data_g]:
                    if isinstance(slot, dict) and slot.get("materia_id") == mid:
                        ore_reali += 1

    ore_da_piazzare = max(0, min(ore_sett - ore_reali, info.get("debito_residuo", 0)))
    if ore_da_piazzare <= 0:
        return

    blocchi_interi = ore_da_piazzare // n
    resto          = ore_da_piazzare %  n

    # --- PIAZZAMENTO BLOCCHI INTERI ---
    for _ in range(blocchi_interi):
        if info["debito_residuo"] <= 0:
            break

        candidati = []

        for key, giorni in cd["giorni_per_key"].items():
            griglia = cd["griglie"][key]

            for g in giorni:
                data_g    = g["data"]
                giorno_it = g["giorno_it"]

                if cd["settimana_per_data"].get(data_g) != settimana:
                    continue

                row = griglia[data_g]

                for h in range(cd["ore_g"]):

                    if _slot_intoccabile(cd, data_g, h):
                        continue
                    if row[h] is not None:
                        continue

                    # blocco intero disponibile?
                    if all(
                        not _slot_intoccabile(cd, data_g, h+k)
                        and row[h+k] is None
                        for k in range(n)
                        if h+k < cd["ore_g"]
                    ) and h+n <= cd["ore_g"]:

                        score = 0

                        # compattazione
                        if h > 0 and row[h-1] is not None:
                            score -= 2
                        if h+n < cd["ore_g"] and row[h+n] is not None:
                            score -= 2

                        # anti‑buco intelligente
                        crea_buco = (
                            h > 0
                            and row[h-1] is None
                            and h+n < cd["ore_g"]
                            and row[h+n] is None
                        )
                        if crea_buco:
                            score += 5

                        centro = cd["ore_g"] // 2
                        score += abs(h - centro)

                        candidati.append((score, crea_buco, h, data_g, key, giorno_it))

        if not candidati:
            break

        candidati.sort(key=lambda x: x[0])
        esiste_senza_buco = any(not c[1] for c in candidati)

        piazzato = False
        for _score, crea_buco, h, data_g, key, giorno_it in candidati:

            if esiste_senza_buco and crea_buco:
                continue

            griglia = cd["griglie"][key]
            row = griglia[data_g]

            if not docente_ok_wrapper(docente_id, data_g, int(h), giorno_it, n):
                continue

            ore_doc = sum(
                1 for slot in row if isinstance(slot, dict) and slot.get("docente_id") == docente_id
            )
            if ore_doc + n > 3:
                continue

            # piazza blocco
            for k in range(n):
                hk = h+k
                piazza_blocco(
                    griglia, data_g, hk, 1,
                    nome_materia, docente_nome, docente_id, None,
                    classe_id=cd["classe"].id,
                    materia_id=mid,
                    tipo="ORDINARIO",
                    origine="ordinario",
                )
                if docente_id:
                    occ.occupa(docente_id, cd["classe"].id, data_g, hk)

                info["debito_residuo"] -= 1
                info["ore_assegnate"]  = info.get("ore_assegnate", 0) + 1

            piazzato = True
            break

        if not piazzato:
            break

    if resto > 0 and info["debito_residuo"] > 0:
        _piazza_soft(cd, docente_ok_wrapper, mid, info)


# ============================================================
#   FASE 3 -- RIEMPIMENTO SOFT
# ============================================================

def fase3_riempimento_soft(cd, docente_ok_wrapper):
    """
    Seconda fase di piazzamento: tenta di piazzare le ore residue una alla
    volta in qualsiasi slot libero dell'intero anno, senza vincolo di blocco.

    Scorre le materie in ordine e per ognuna chiama _piazza_soft finche'
    il debito e' esaurito o nessuno slot e' disponibile.
    """
    for mid, info in cd["materie_attive"].items():
        while info.get("debito_residuo", 0) > 0:
            if not _piazza_soft(cd, docente_ok_wrapper, mid, info):
                break


def _piazza_soft(cd, docente_ok_wrapper, mid, info):
    """
    Piazza una singola ora di una materia nel primo slot libero disponibile.

    Vincoli rispettati:
    - Slot non intoccabile (no STAGE/FESTA/SPECIALE/FISSO)
    - Docente disponibile (globale + orario)
    - Docente non supera 3 ore nella stessa giornata

    Restituisce True se l'ora e' stata piazzata, False altrimenti.
    """
    docente_id   = info.get("docente_id")
    docente_nome = info.get("docente_nome", "")
    nome_materia = info["nome"]

    for key, giorni in cd["giorni_per_key"].items():
        griglia = cd["griglie"][key]

        for g in giorni:
            data_g    = g["data"]
            giorno_it = g["giorno_it"]

            row = griglia[data_g]

            for h in range(cd["ore_g"]):

                if _slot_intoccabile(cd, data_g, h):
                    continue
                if row[h] is not None:
                    continue

                if not docente_ok_wrapper(docente_id, data_g, int(h), giorno_it, 1):
                    continue

                ore_doc = sum(
                    1 for slot in row if isinstance(slot, dict) and slot.get("docente_id") == docente_id
                )
                if ore_doc >= 3:
                    continue

                piazza_blocco(
                    griglia, data_g, h, 1,
                    nome_materia, docente_nome, docente_id, None,
                    classe_id=cd["classe"].id,
                    materia_id=mid,
                    tipo="ORDINARIO",
                    origine="ordinario",
                )
                if docente_id:
                    occ.occupa(docente_id, cd["classe"].id, data_g, h)

                info["debito_residuo"] -= 1
                info["ore_assegnate"]  = info.get("ore_assegnate", 0) + 1
                return True

    return False


# ============================================================
#   FASE 4 -- ULTRA-SOFT
# ============================================================

def fase4_riempimento_ultrasoft(cd, docente_ok_wrapper):
    """
    Terza fase: identica a fase3 ma con un secondo tentativo completo.

    Utile nei casi in cui le prime fasi hanno lasciato debi piccoli che non
    trovano posto per via della priorita' di ordinamento. Stessa logica di
    _piazza_soft ma su tutto l'anno, senza vincoli diversi.
    """
    for mid, info in cd["materie_attive"].items():
        while info.get("debito_residuo", 0) > 0:
            if not _piazza_ultrasoft(cd, docente_ok_wrapper, mid, info):
                break


def _piazza_ultrasoft(cd, docente_ok_wrapper, mid, info):
    docente_id   = info.get("docente_id")
    docente_nome = info.get("docente_nome", "")
    nome_materia = info["nome"]

    for key, giorni in cd["giorni_per_key"].items():
        griglia = cd["griglie"][key]

        for g in giorni:
            data_g    = g["data"]
            giorno_it = g["giorno_it"]

            row = griglia[data_g]

            for h in range(cd["ore_g"]):

                if _slot_intoccabile(cd, data_g, h):
                    continue
                if row[h] is not None:
                    continue

                if not docente_ok_wrapper(docente_id, data_g, int(h), giorno_it, 1):
                    continue

                ore_doc = sum(
                    1 for slot in row if isinstance(slot, dict) and slot.get("docente_id") == docente_id
                )
                if ore_doc >= 3:
                    continue

                piazza_blocco(
                    griglia, data_g, h, 1,
                    nome_materia, docente_nome, docente_id, None,
                    classe_id=cd["classe"].id,
                    materia_id=mid,
                    tipo="ORDINARIO",
                    origine="ordinario",
                )
                if docente_id:
                    occ.occupa(docente_id, cd["classe"].id, data_g, h)

                info["debito_residuo"] -= 1
                info["ore_assegnate"]  = info.get("ore_assegnate", 0) + 1
                return True

    return False

# ============================================================
#   FASE 5 -- RIEMPIMENTO FORZATO (SOLO PER ORE NON PIAZZATE)
# ============================================================

def fase5_riempimento_forzato(cd):
    """
    Piazza le ore residue ignorando i vincoli docente,
    ma rispettando:
    - giorni speciali (STAGE, FESTA, SPECIALE)
    - slot fissi
    - slot speciali
    - slot già occupati
    NON modifica ore già piazzate.
    """
    for mid, info in cd["materie_attive"].items():
        while info.get("debito_residuo", 0) > 0:
            if not _piazza_forzato(cd, mid, info):
                break


def _piazza_forzato(cd, mid, info):
    docente_id   = info.get("docente_id")
    docente_nome = info.get("docente_nome", "")
    nome_materia = info["nome"]

    for key, giorni in cd["giorni_per_key"].items():
        griglia = cd["griglie"][key]

        for g in giorni:
            data_g    = g["data"]
            row       = griglia[data_g]

            for h in range(cd["ore_g"]):

                # NON tocco slot intoccabili (giorni speciali, fissi, speciali)
                if _slot_intoccabile(cd, data_g, h):
                    continue

                # serve un buco reale
                if row[h] is not None:
                    continue

                # piazza ignorando docente_ok_wrapper e limiti ore_doc
                piazza_blocco(
                    griglia, data_g, h, 1,
                    nome_materia, docente_nome, docente_id, None,
                    classe_id=cd["classe"].id,
                    materia_id=mid,
                    tipo="FORZATO",
                    origine="ordinario_forzato",
                )

                # NON occupo il docente globalmente → non genero conflitti
                # (questo è voluto: fase di emergenza)

                info["debito_residuo"] -= 1
                info["ore_assegnate"]  = info.get("ore_assegnate", 0) + 1
                return True

    return False



# ============================================================
#   REPORT
# ============================================================

def report_classe(cd):
    """
    Stampa un riepilogo della pianificazione per la classe:
    - ore totali previste vs piazzate vs residue
    - percentuale di completamento
    - numero di buchi interni nella giornata

    Un "buco interno" e' uno slot vuoto tra due slot occupati nello stesso
    giorno (indicatore di qualita' del piazzamento).
    """
    classe = cd["classe"]
    materie = cd["materie_attive"]

    ore_totali = sum(info.get("ore_annuali", 0) for info in materie.values())
    ore_piazzate = sum(info.get("ore_assegnate", 0) for info in materie.values())
    ore_residue = sum(info.get("debito_residuo", 0) for info in materie.values())

    buchi = 0
    for _, griglia in cd["griglie"].items():
        for _, row in griglia.items():
            for h in range(1, cd["ore_g"] - 1):
                if row[h] is None and row[h-1] is not None and row[h+1] is not None:
                    buchi += 1

    percentuale = round((ore_piazzate / ore_totali) * 100, 2) if ore_totali > 0 else 0

    print(f"\n===== REPORT CLASSE {classe.nome_classe} =====")
    print(f"Ore totali previste: {ore_totali}")
    print(f"Ore piazzate:        {ore_piazzate}")
    print(f"Ore residue:         {ore_residue}")
    print(f"Completamento:       {percentuale}%")
    print(f"Buchi interni:       {buchi}")
    print("=========================================\n")
