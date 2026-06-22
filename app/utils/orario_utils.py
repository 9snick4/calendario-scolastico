# app/utils/orario_utils.py

from datetime import datetime, date, time, timedelta
from collections import defaultdict

from app.models import VincoloDocente, GiornoSpeciale, Stage, Festivita, Docente
import app.utils.occupazione as occ

print(">>> CARICATO orario_utils.py VERSIONE NUOVA")


# ===============================
# NORMALIZZAZIONE GIORNI
# ===============================

def normalizza_giorno_it(g):
    if not g:
        return None
    g = g.strip().lower()
    mapping = {
        "lunedì": "Lunedì", "lunedi": "Lunedì", "lun": "Lunedì",
        "martedì": "Martedì", "martedi": "Martedì", "mar": "Martedì",
        "mercoledì": "Mercoledì", "mercoledi": "Mercoledì", "mer": "Mercoledì",
        "giovedì": "Giovedì", "giovedi": "Giovedì", "gio": "Giovedì",
        "venerdì": "Venerdì", "venerdi": "Venerdì", "ven": "Venerdì",
        "sabato": "Sabato", "sab": "Sabato",
        "domenica": "Domenica", "dom": "Domenica",
    }
    return mapping.get(g, g)


def label_giorno_it(dt):
    mapping_it = {
        "Monday": "Lunedì",
        "Tuesday": "Martedì",
        "Wednesday": "Mercoledì",
        "Thursday": "Giovedì",
        "Friday": "Venerdì",
        "Saturday": "Sabato",
        "Sunday": "Domenica",
    }
    return mapping_it.get(dt.strftime("%A"), dt.strftime("%A"))


# ===============================
# ORARI E SLOT
# ===============================

ORA_INIZIO_LEZIONI = time(8, 0)
DURATA_ORA_MINUTI = 60


def orario_slot(index_ora):
    start_dt = datetime.combine(date.today(), ORA_INIZIO_LEZIONI) + timedelta(
        minutes=DURATA_ORA_MINUTI * index_ora
    )
    return start_dt.time()


def intervalli_si_sovrappongono(inizio1, fine1, inizio2, fine2):
    return inizio1 < fine2 and inizio2 < fine1


# ===============================
# FESTIVITÀ
# ===============================

def giorno_festivo(data):
    festivita = Festivita.query.all()
    for f in festivita:
        if f.data_inizio <= data <= f.data_fine:
            return True
    return False


# ===============================
# DISPONIBILITÀ DOCENTI
# ===============================

def docente_disponibile(docente_id, giorno_label, index_ora):
    """
    Ritorna True se il docente è disponibile in quel giorno/ora
    secondo i VincoloDocente.
    """
    if not docente_id:
        return True

    slot_start = orario_slot(index_ora)
    slot_end_dt = datetime.combine(date.today(), slot_start) + timedelta(
        minutes=DURATA_ORA_MINUTI
    )
    slot_end = slot_end_dt.time()

    vincoli = VincoloDocente.query.filter_by(docente_id=docente_id).all()
    if not vincoli:
        return True

    giorno_norm = normalizza_giorno_it(giorno_label)

    vincoli_giorno = [
        v for v in vincoli
        if normalizza_giorno_it(v.giorno) == giorno_norm
    ]

    # Se esistono vincoli ma nessuno per quel giorno → non disponibile
    if not vincoli_giorno:
        return False

    for v in vincoli_giorno:
        ora_da = v.ora_da
        ora_a = v.ora_a

        if isinstance(ora_da, str):
            ora_da = datetime.strptime(ora_da, "%H:%M").time()
        if isinstance(ora_a, str):
            ora_a = datetime.strptime(ora_a, "%H:%M").time()

        if intervalli_si_sovrappongono(slot_start, slot_end, ora_da, ora_a):
            return True

    return False


# ===============================
# STAGE
# ===============================

def classe_in_stage_giorno(classe_id, data):
    stage = Stage.query.filter_by(classe_id=classe_id).first()
    if not stage:
        return False

    in_primo_periodo = (
        stage.periodo_stage_1_da and stage.periodo_stage_1_a and
        stage.periodo_stage_1_da <= data <= stage.periodo_stage_1_a
    )

    in_secondo_periodo = (
        stage.periodo_stage_2_da and stage.periodo_stage_2_a and
        stage.periodo_stage_2_da <= data <= stage.periodo_stage_2_a
    )

    if not (in_primo_periodo or in_secondo_periodo):
        return False

    if not stage.giorni_stage:
        return True

    giorno_it = normalizza_giorno_it(label_giorno_it(data))

    giorni_raw = stage.giorni_stage.replace(";", ",").replace("/", ",")
    giorni_split = [g.strip() for g in giorni_raw.split(",") if g.strip()]
    giorni_norm = [normalizza_giorno_it(g) for g in giorni_split]

    return giorno_it in giorni_norm


# ===============================
# GIORNI SPECIALI
# ===============================

from sqlalchemy import func
from app.models import GiornoSpeciale

def giorno_speciale_classe(classe_id, data_giorno):
    return GiornoSpeciale.query.filter(
        GiornoSpeciale.classe_id == classe_id,
        func.date(GiornoSpeciale.data) == data_giorno
    ).first()


# ===============================
# PERIODO CLASSE
# ===============================

def periodo_classe(classe, anno):
    if not classe.data_inizio or not classe.data_fine:
        return None, None

    data_inizio = classe.data_inizio
    data_fine = classe.data_fine

    if data_inizio > data_fine:
        data_inizio, data_fine = data_fine, data_inizio

    return data_inizio, data_fine




# ===============================
# SLOT E BLOCCHI
# ===============================

def slot_libero(griglia, data, start, blocco):
    for i in range(start, start + blocco):
        if griglia[data][i] is not None:
            return False
    return True


def piazza_blocco(
    griglia,
    data,
    start,
    blocco,
    materia,
    docente,
    docente_id,
    occupazione_docenti,
    classe_id=None,
    materia_id=None,
    tipo="NORMALE",
    origine="ordinario"
):
    """
    Piazza un blocco nella griglia e aggiorna l’occupazione globale.
    """

    # Normalizza id docente
    try:
        docente_id_norm = int(docente_id) if docente_id is not None else None
    except Exception:
        docente_id_norm = None

    docente_obj = Docente.query.get(docente_id_norm) if docente_id_norm else None
    docente_nome_effettivo = docente_obj.nome_docente if docente_obj else docente

    # --- PIAZZAMENTO NELLA GRIGLIA ---
    for i in range(start, start + blocco):
        griglia[data][i] = {
            "materia": materia,
            "materia_id": materia_id,
            "docente": docente_nome_effettivo or "",
            "docente_id": docente_id_norm,
            "classe_id": classe_id,
            "tipo": tipo,
            "origine": origine,
            "blocco": blocco,
            "fisso": (tipo == "FISSO"),
        }

    # --- DOC EST → non occupa globalmente ---
    if docente_nome_effettivo == "DOC EST":
        return

    # --- AGGIORNA OCCUPAZIONE GLOBALE DOCENTI ---
    if docente_id_norm:
        for i in range(start, start + blocco):
            occ.occupa(docente_id_norm, classe_id, data, i)

    # --- AGGIORNA OCCUPAZIONE GLOBALE CLASSI ---
    if classe_id:
        occ.OCCUPAZIONE_CLASSI_GLOBALE.setdefault(classe_id, {})
        occ.OCCUPAZIONE_CLASSI_GLOBALE[classe_id].setdefault(data, set())
        for i in range(start, start + blocco):
            occ.OCCUPAZIONE_CLASSI_GLOBALE[classe_id][data].add(i)

    # --- AGGIORNA OCCUPAZIONE LOCALE (legacy) ---
    if occupazione_docenti is not None and docente_id_norm:
        occupazione_docenti.setdefault(docente_id_norm, {})
        occupazione_docenti[docente_id_norm].setdefault(data, set())
        for i in range(start, start + blocco):
            occupazione_docenti[docente_id_norm][data].add(i)



# ===============================
# COSTRUZIONE GRIGLIA E SETTIMANA
# ===============================

def crea_griglia_settimanale(giorni_settimana, ore_giornaliere):
    return {g["data"]: [None for _ in range(ore_giornaliere)] for g in giorni_settimana}


def costruisci_settimana(griglia, giorni_settimana, ore_giornaliere, calendario):
    """
    Converte la griglia interna (perfetta) nel calendario finale,
    preservando TUTTE le informazioni necessarie al validatore:
    - docente_id
    - fisso
    - blocco (1 ora per slot, il validatore ricostruisce)
    Gli slot SPECIALE_VUOTO (buchi intenzionali nei giorni speciali)
    vengono convertiti in slot vuoti normali.
    """
    for g in giorni_settimana:
        data_g = g["data"]
        giorno_it = g["giorno_it"]

        lezioni = []

        for idx in range(ore_giornaliere):
            slot = griglia[data_g][idx]
            ora = orario_slot(idx)

            if slot is None or slot.get("tipo") == "SPECIALE_VUOTO":
                lezioni.append({
                    "ora": ora,
                    "materia": "",
                    "docente": "",
                    "docente_id": None,
                    "fisso": False,
                    "blocco": 1,
                })
            else:
                lezioni.append({
                    "ora": ora,
                    "materia": slot.get("materia", ""),
                    "docente": slot.get("docente", ""),
                    "docente_id": slot.get("docente_id"),
                    "fisso": slot.get("fisso", False),
                    "blocco": 1,
                })

        calendario.append({
            "data": data_g,
            "giorno_settimana": giorno_it,
            "lezioni": lezioni,
        })

# ===============================
# SALVATAGGIO + SINCRONIZZAZIONE
# ===============================

def salva_calendari(classi_info):
    calendario_per_classe = {}

    for cid, info in classi_info.items():
        classe = info["classe"]
        calendario_per_classe[cid] = {
            "nome_classe": classe.nome_classe,
            "ore_giornaliere": info["ore_giornaliere"],
            "calendario": info["calendario"],
        }

    return calendario_per_classe


def sincronizza_classi_associate(calendario_per_classe, classi, nomi_non_prof):
    """
    Copia SOLO le materie non professionali dalla classe principale
    alla classe associata, SENZA mai sovrascrivere lezioni già piazzate
    e SENZA creare conflitti.
    """

    doc_est = Docente.query.filter_by(nome_docente="DOC EST").first()
    nome_doc_est = doc_est.nome_docente if doc_est else "DOC EST"

    classi_map = {c.id: c for c in classi}

    for classe in classi:
        if not classe.classe_associata_id:
            continue

        principale = classe.classe_associata_id
        associata = classe.id

        cal_princ = calendario_per_classe[principale]["calendario"]
        cal_assoc = calendario_per_classe[associata]["calendario"]

        giorni = min(len(cal_princ), len(cal_assoc))

        for idx_giorno in range(giorni):
            lez_p = cal_princ[idx_giorno]["lezioni"]
            lez_a = cal_assoc[idx_giorno]["lezioni"]

            ore = min(len(lez_p), len(lez_a))

            for i in range(ore):
                materia_p = lez_p[i]["materia"]

                # Copia solo materie non professionali
                if not materia_p or materia_p not in nomi_non_prof:
                    continue

                # NON sovrascrivere lezioni già piazzate
                if lez_a[i]["materia"]:
                    continue

                # NON invadere STAGE o FESTA
                if lez_a[i]["materia"] in ("STAGE", "FESTA"):
                    continue

                # NON invadere slot fissi o speciali
                if lez_a[i].get("fisso"):
                    continue

                # Copia sicura
                lez_a[i]["materia"] = materia_p
                lez_a[i]["docente"] = nome_doc_est
                lez_a[i]["docente_id"] = None
                lez_a[i]["fisso"] = False
