# app/utils/occupazione.py

from collections import defaultdict

# ============================================================
# 1) OCCUPAZIONE DOCENTI (fonte di verità per conflitti reali)
# docente_id → data → ora → classe_id
# ============================================================

# docente_id -> data -> {ora: classe_id}
# Fonte di verita' per i conflitti reali tra docenti.
# Viene resettata all'inizio di ogni genera_calendario_annuale().
OCCUPAZIONE_DOCENTI_GLOBALE = defaultdict(
    lambda: defaultdict(dict)
)

# ============================================================
# 2) OCCUPAZIONE CLASSI (STAGE, FESTA, SPECIALI, ecc.)
# classe_id → data → ora → True
# ============================================================

# classe_id -> data -> {ora: True}
# Traccia gli slot occupati da STAGE, FESTA o SPECIALE per una classe.
OCCUPAZIONE_CLASSI_GLOBALE = defaultdict(
    lambda: defaultdict(dict)
)


# ============================================================
# 3) FUNZIONI DOCENTE
# ============================================================

def docente_libero(docente_id, data, ora):
    """
    True se il docente NON è occupato globalmente in quella data/ora.
    """
    if not docente_id:
        return True

    return ora not in OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data]


def occupa(docente_id, classe_id, data, ora):
    """
    Registra l'occupazione di uno slot orario per un docente.

    Salva nella mappa globale: docente_id -> data -> ora -> classe_id.
    Se docente_id e' None non fa nulla.
    """
    if not docente_id:
        return

    OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data][ora] = classe_id


def libera(docente_id, data, ora):
    """
    Rimuove l'occupazione di uno slot per un docente (usato durante i
    ribilanciamenti fasi 6/7/8 per spostare blocchi).
    """
    if not docente_id:
        return

    if ora in OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data]:
        del OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data][ora]


# ============================================================
# 4) FUNZIONI CLASSE
# ============================================================

def classe_occupata(classe_id, data, ora):
    """
    True se la classe è occupata (STAGE, FESTA, SPECIALE, ecc.)
    """
    return ora in OCCUPAZIONE_CLASSI_GLOBALE[classe_id][data]


def occupa_classe(classe_id, data, ora):
    """
    Marca uno slot come occupato per la classe (STAGE, FESTA, ecc.).
    """
    OCCUPAZIONE_CLASSI_GLOBALE[classe_id][data][ora] = True


def libera_classe(classe_id, data, ora):
    """
    Rimuove l'occupazione di uno slot per la classe.
    """
    if ora in OCCUPAZIONE_CLASSI_GLOBALE[classe_id][data]:
        del OCCUPAZIONE_CLASSI_GLOBALE[classe_id][data][ora]


# ============================================================
# 5) RICOSTRUZIONE GLOBALE COMPLETA
# ============================================================

def rebuild_global_occupation(griglie, settimane_classe, ore_giornaliere):
    """
    Ricostruisce OCCUPAZIONE_DOCENTI_GLOBALE a partire dalle griglie
    di UNA SINGOLA CLASSE.

    Struttura attesa:
    griglie = {
        (anno, settimana): {
            data: [slot, slot, slot, ...]   # SEMPRE LISTE
        }
    }

    settimane_classe non viene usato: la fonte di verità sono le griglie.
    """

    OCCUPAZIONE_DOCENTI_GLOBALE.clear()
    OCCUPAZIONE_CLASSI_GLOBALE.clear()

    def process_griglia(griglia_sett):
        """
        griglia_sett: dict[data] -> list[slot]
        Normalizza eventuali righe errate e registra l’occupazione.
        """
        for data, row in griglia_sett.items():

            # 🔥 Normalizzazione: row DEVE essere una LISTA
            if isinstance(row, dict):
                # Convertiamo dict → list preservando gli indici
                max_idx = max(row.keys()) if row else -1
                row = [row.get(i) for i in range(max_idx + 1)]
                griglia_sett[data] = row

            if not isinstance(row, list):
                continue

            # 🔥 Iteriamo solo sulle ore realmente presenti
            for ora in range(len(row)):
                slot = row[ora]

                if not isinstance(slot, dict):
                    continue

                docente_id = slot.get("docente_id")
                if not docente_id:
                    continue

                # Ignora DOC EST
                nome_doc = slot.get("docente", "") or ""
                if "DOC EST" in nome_doc:
                    continue

                # 🔥 Registra occupazione docente
                OCCUPAZIONE_DOCENTI_GLOBALE[docente_id].setdefault(data, {})
                OCCUPAZIONE_DOCENTI_GLOBALE[docente_id][data][ora] = True

    # 🔥 Caso 1: griglie è già una griglia settimanale (data → list)
    if all(isinstance(v, list) for v in griglie.values()):
        process_griglia(griglie)
        return

    # 🔥 Caso 2: griglie = { key_settimana → griglia_settimanale }
    for griglia_sett in griglie.values():
        process_griglia(griglia_sett)
