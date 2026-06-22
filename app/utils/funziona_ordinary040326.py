# app/utils/ordinary_placement.py
#
# Motore PuLP per il piazzamento ordinario delle ore.
#
# Architettura a due fasi:
# ─────────────────────────
# FASE 1 — PuLP (LpMaximize): piazza il massimo rispettando tutti i vincoli
#           di forma (pattern mattina, blocchi consecutivi, max ore docente,
#           pomeriggi mensili, almeno 4 consecutive per giornata).
#
# FASE 2 — Greedy fallback: per il debito residuo dopo la Fase 1, piazza
#           le ore rimaste slot per slot, rispettando SOLO:
#             • disponibilità docenti da DB (docente_ok_wrapper)
#             • occupazione cross-classi (occ.docente_libero)
#             • slot non già occupati (libero e non ancora assegnato)
#             • giorni bloccati (STAGE/FESTA/SPECIALE) intoccabili
#           I vincoli di forma (pattern, buchi, pomeriggi, ecc.) vengono
#           ignorati per garantire il piazzamento del 100% delle ore.
#
# Regole di protezione slot
# ─────────────────────────
# • STAGE / FESTA    → bloccano l'INTERA giornata.
# • SPECIALE         → blocca l'INTERA giornata.
# • FISSO            → blocca SOLO SE STESSO; gli slot liberi della stessa
#                      giornata sono disponibili per entrambe le fasi.

from datetime import date
from collections import defaultdict

import pulp

from app.utils.orario_utils import piazza_blocco
import app.utils.occupazione as occ

# ──────────────────────────────────────────────────────────────
# CONFIGURAZIONE
# ──────────────────────────────────────────────────────────────

CUTOFF_MARZO               = (3, 1)
MAX_ORE_DOCENTE_PER_GIORNO = 2
ORE_MATTINA_MAX            = 6
MAX_POMERIGGI_AL_MESE      = 1


# ──────────────────────────────────────────────────────────────
# HELPER
# ──────────────────────────────────────────────────────────────

def ore_minime_giornata(data_g: date) -> int:
    cutoff = date(data_g.year, *CUTOFF_MARZO)
    return 6 if data_g < cutoff else 4


def _tipo_slot(slot) -> str:
    if slot is None:
        return "libero"
    if not isinstance(slot, dict):
        return "libero"
    tipo    = slot.get("tipo", "")
    origine = slot.get("origine", "")
    fisso   = slot.get("fisso", False)
    if tipo in ("STAGE", "FESTA"):
        return "stage_festa"
    if tipo in ("SPECIALE", "SPECIALE_VUOTO") or origine == "speciale":
        return "speciale"
    if tipo == "FISSO" or origine == "fisso" or fisso:
        return "fisso"
    return "ordinario"


def giornata_bloccata_interamente(row, ore_giornaliere) -> bool:
    for h in range(ore_giornaliere):
        s = row[h] if h < len(row) else None
        if _tipo_slot(s) in ("stage_festa", "speciale"):
            return True
    return False


def docente_disponibile_global(docente_id, data, ora,
                                giorno_it=None, docente_ok=None) -> bool:
    if not docente_id or docente_id == "DOC EST":
        return True
    if not occ.docente_libero(docente_id, data, ora):
        return False
    if docente_ok:
        if not giorno_it:
            giorno_it = data.strftime("%A")
        if not docente_ok(docente_id, data, giorno_it, ora, 1):
            return False
    return True


def _giorni_per_mese(days):
    mesi = defaultdict(list)
    for d in days:
        mesi[(d.year, d.month)].append(d)
    return mesi


# ──────────────────────────────────────────────────────────────
# FASE 2 — GREEDY FALLBACK
# ──────────────────────────────────────────────────────────────

def _greedy_fallback(
    griglie,
    giorni_per_key,
    bloccata,
    libero_originale,
    classe,
    materie_attive,
    ore_giornaliere,
    docente_ok_wrapper,
):
    """
    Piazza il debito residuo in materie_attive usando una strategia greedy.
    Rispetta solo: disponibilità docenti, slot liberi non ancora occupati,
    giorni bloccati. Ignora tutti i vincoli di forma.
    Modifica griglie e materie_attive in-place.
    """
    # Costruisce lista ordinata: (data, h) liberi e ancora vuoti dopo Fase 1
    # Ordina per data poi per ora per avere un piazzamento deterministico
    slot_disponibili = []
    for key, giorni in giorni_per_key.items():
        griglia = griglie[key]
        for g in giorni:
            data_g = g["data"]
            if bloccata[data_g]:
                continue
            row = griglia[data_g]
            for h in range(ore_giornaliere):
                if not libero_originale.get((data_g, h), False):
                    continue
                # Slot libero originalmente: controlla se è ancora vuoto dopo Fase 1
                s = row[h] if h < len(row) else None
                if s is None:
                    slot_disponibili.append((data_g, h, key, g["giorno_it"]))

    slot_disponibili.sort(key=lambda t: (t[0], t[1]))

    # Per ogni materia con debito residuo, scorre gli slot e piazza
    for mid, info in materie_attive.items():
        debito = info.get("debito_residuo", 0)
        if debito <= 0:
            continue

        docente_id   = info.get("docente_id")
        docente_nome = info.get("docente_nome", "")
        nome_materia = info["nome"]

        piazzate_greedy = 0
        slot_usati = []

        for idx, (data_g, h, key, giorno_it) in enumerate(slot_disponibili):
            if debito <= 0:
                break

            griglia = griglie[key]
            row = griglia[data_g]

            # Controlla che lo slot sia ancora vuoto (un'altra materia potrebbe
            # averlo occupato in un'iterazione precedente di questo stesso loop)
            s = row[h] if h < len(row) else None
            if s is not None:
                continue

            # Controlla disponibilità docente
            if not docente_disponibile_global(
                docente_id, data_g, h, giorno_it, docente_ok_wrapper
            ):
                continue

            # Piazza
            piazza_blocco(
                griglia, data_g, h, 1,
                nome_materia, docente_nome, docente_id, None,
                classe_id=classe.id,
                materia_id=mid,
                tipo="ORDINARIO_GREEDY",
                origine="ordinario_greedy",
            )
            if docente_id:
                occ.occupa(docente_id, classe.id, data_g, h)

            info["debito_residuo"] = max(0, info.get("debito_residuo", 0) - 1)
            info["ore_assegnate"]  = info.get("ore_assegnate", 0) + 1
            debito -= 1
            piazzate_greedy += 1
            slot_usati.append(idx)

        if piazzate_greedy:
            print(f"  [GREEDY] {classe.nome_classe} '{nome_materia}': "
                  f"+{piazzate_greedy} ore, debito_residuo={info.get('debito_residuo',0)}")

        if info.get("debito_residuo", 0) > 0:
            print(f"  [GREEDY WARN] {classe.nome_classe} '{nome_materia}': "
                  f"debito non azzerato, rimangono {info['debito_residuo']} ore. "
                  f"Docente esaurito o slot insufficienti.")


# ──────────────────────────────────────────────────────────────
# MOTORE PRINCIPALE
# ──────────────────────────────────────────────────────────────

def apply_ordinary_pulp(
    griglie,
    settimane_classe,
    classe,
    materie_info,
    materie_dict,
    docenti_dict,
    docente_ok_wrapper,
):
    ore_giornaliere = classe.ore_massime_giornaliere or 6

    # ── 1) Timeline ────────────────────────────────────────────
    giorni_per_key = {}
    all_days = []
    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda g: g["data"])
        giorni_per_key[key] = giorni
        for g in giorni:
            all_days.append(g["data"])

    # ── 2) Analisi slot ────────────────────────────────────────
    bloccata    = {}
    fixed_slots = {}
    libero      = {}

    for key, giorni in giorni_per_key.items():
        griglia = griglie[key]
        for g in giorni:
            data_g = g["data"]
            row    = griglia[data_g]
            bl = giornata_bloccata_interamente(row, ore_giornaliere)
            bloccata[data_g] = bl
            for h in range(ore_giornaliere):
                s = row[h] if h < len(row) else None
                t = _tipo_slot(s)
                if bl:
                    if s is not None:
                        fixed_slots[(data_g, h)] = s
                    libero[(data_g, h)] = False
                elif t == "fisso":
                    fixed_slots[(data_g, h)] = s
                    libero[(data_g, h)] = False
                elif t == "libero":
                    libero[(data_g, h)] = True
                else:
                    libero[(data_g, h)] = False

    giorni_ordinari = [d for d in all_days if not bloccata[d]]

    # ── 3) Materie con debito ──────────────────────────────────
    materie_attive = {
        mid: info
        for mid, info in materie_info.items()
        if info.get("debito_residuo", 0) > 0
    }

    # ── DIAGNOSTICA ────────────────────────────────────────────
    n_bloccati = sum(1 for v in bloccata.values() if v)
    n_liberi   = sum(1 for v in libero.values() if v)
    tot_debito = sum(i.get("debito_residuo", 0) for i in materie_attive.values())
    print(f"[PULP] {classe.nome_classe}: "
          f"giorni_tot={len(all_days)} bloccati={n_bloccati} ordinari={len(giorni_ordinari)} | "
          f"slot_liberi={n_liberi} debito_tot={tot_debito} materie_attive={len(materie_attive)}")
    for mid, info in materie_attive.items():
        print(f"  [PULP]   mid={mid} '{info['nome']}' "
              f"debito={info.get('debito_residuo',0)} blocco={info.get('blocco_orario',1)}")

    if not materie_attive:
        print(f"[INFO] Nessun debito residuo per {classe.nome_classe}, skip.")
        return griglie

    if not giorni_ordinari:
        print(f"[WARN] Nessun giorno ordinario per {classe.nome_classe} (tutti STAGE/FESTA/SPECIALE).")
        return griglie

    materia_docente = {mid: info.get("docente_id") for mid, info in materie_attive.items()}
    materia_blocco  = {
        mid: max(info.get("blocco_orario", 1), info.get("ore_minime_consecutive", 1))
        for mid, info in materie_attive.items()
    }

    # ── 4) Modello PuLP ────────────────────────────────────────
    prob = pulp.LpProblem(f"Orario_{classe.nome_classe}", pulp.LpMaximize)

    y  = {}
    x  = {}
    z  = {}
    c  = {}
    pm = {}

    for data_g in all_days:
        for h in range(ore_giornaliere):
            yv = pulp.LpVariable(f"y_{data_g}_{h}", 0, 1, pulp.LpBinary)
            y[(data_g, h)] = yv
            if bloccata[data_g]:
                prob += yv == (1 if (data_g, h) in fixed_slots else 0)
            elif (data_g, h) in fixed_slots:
                prob += yv == 1
        pmv = pulp.LpVariable(f"pm_{data_g}", 0, 1, pulp.LpBinary)
        pm[data_g] = pmv
        if bloccata[data_g]:
            prob += pmv == 0

    for data_g in giorni_ordinari:
        for h in range(ore_giornaliere):
            if libero.get((data_g, h), False):
                for mid in materie_attive:
                    x[(mid, data_g, h)] = pulp.LpVariable(
                        f"x_{mid}_{data_g}_{h}", 0, 1, pulp.LpBinary
                    )
            if h <= ore_giornaliere - 4:
                c[(data_g, h)] = pulp.LpVariable(f"c_{data_g}_{h}", 0, 1, pulp.LpBinary)
        for mid in materie_attive:
            L = materia_blocco[mid]
            for h in range(ore_giornaliere - L + 1):
                if all(libero.get((data_g, h + k), False) for k in range(L)):
                    z[(mid, data_g, h)] = pulp.LpVariable(
                        f"z_{mid}_{data_g}_{h}", 0, 1, pulp.LpBinary
                    )

    # ── 5) Vincoli ─────────────────────────────────────────────

    def xs(data_g, h):
        return [x[(mid, data_g, h)] for mid in materie_attive if (mid, data_g, h) in x]

    # 5.1) y ↔ x per slot liberi
    for data_g in giorni_ordinari:
        for h in range(ore_giornaliere):
            if (data_g, h) in fixed_slots:
                continue
            xlist = xs(data_g, h)
            if xlist:
                prob += y[(data_g, h)] == pulp.lpSum(xlist)
            else:
                prob += y[(data_g, h)] == 0

    # 5.2) Un solo ordinario per slot
    for data_g in giorni_ordinari:
        for h in range(ore_giornaliere):
            xlist = xs(data_g, h)
            if xlist:
                prob += pulp.lpSum(xlist) <= 1

    # 5.3) Debito materia <= debito (non ==)
    for mid, info in materie_attive.items():
        debito = info.get("debito_residuo", 0)
        xall   = [x[(mid, d, h)] for (m, d, h) in x if m == mid]
        if not xall:
            print(f"[WARN] {classe.nome_classe}: '{info['nome']}' debito={debito} nessuno slot libero.")
            continue
        prob += pulp.lpSum(xall) <= debito

    # 5.4) Blocchi consecutivi
    for (mid, data_g, h0), varz in z.items():
        L = materia_blocco[mid]
        for k in range(L):
            if (mid, data_g, h0 + k) in x:
                prob += x[(mid, data_g, h0 + k)] >= varz

    # 5.5) Max MAX_ORE_DOCENTE_PER_GIORNO per docente per giornata
    for data_g in giorni_ordinari:
        doc_vars = defaultdict(list)
        for (mid, d, h), var in x.items():
            if d != data_g:
                continue
            did = materia_docente.get(mid)
            if did:
                doc_vars[did].append(var)
        for did, vlist in doc_vars.items():
            prob += pulp.lpSum(vlist) <= MAX_ORE_DOCENTE_PER_GIORNO

    # 5.6) Max 2 ore consecutive per docente (finestra di 3)
    for data_g in giorni_ordinari:
        for h in range(ore_giornaliere - 2):
            doc_vars = defaultdict(list)
            for (mid, d, hh), var in x.items():
                if d != data_g or hh < h or hh > h + 2:
                    continue
                did = materia_docente.get(mid)
                if did:
                    doc_vars[did].append(var)
            for did, vlist in doc_vars.items():
                prob += pulp.lpSum(vlist) <= 2

    # 5.7) RIMOSSO — minimo ore assoluto per giornata

    # 5.8) Almeno 4 slot occupati consecutivi (fissi + ordinari) per giornata
    for data_g in giorni_ordinari:
        poss = []
        for h in range(ore_giornaliere - 3):
            if (data_g, h) not in c:
                continue
            cv = c[(data_g, h)]
            poss.append(cv)
            prob += cv <= y[(data_g, h)]
            prob += cv <= y[(data_g, h + 1)]
            prob += cv <= y[(data_g, h + 2)]
            prob += cv <= y[(data_g, h + 3)]
            prob += cv >= (y[(data_g, h)] + y[(data_g, h + 1)] +
                           y[(data_g, h + 2)] + y[(data_g, h + 3)] - 3)
        if poss:
            prob += pulp.lpSum(poss) >= 1

    # 5.9) RIMOSSO — no buco 1-0-1
    # 5.10) RIMOSSO — no ora isolata

    # 5.11) Pattern mattina: 111111 / 111110 / 111100 / 011111 / 001111
    n_mat       = min(ORE_MATTINA_MAX, ore_giornaliere)
    MAX_LEADING  = 2
    MAX_TRAILING = 2
    coda_start   = n_mat - 1 - MAX_TRAILING

    for data_g in giorni_ordinari:
        for k in range(MAX_LEADING + 1, n_mat):
            prob += (pulp.lpSum(y[(data_g, h)] for h in range(MAX_LEADING + 1))
                     >= y[(data_g, k)])
        for k in range(coda_start):
            prob += (pulp.lpSum(y[(data_g, h)] for h in range(coda_start, n_mat))
                     >= y[(data_g, k)])

    # 5.12) Max MAX_POMERIGGI_AL_MESE pomeriggi al mese
    pom_slots = list(range(ORE_MATTINA_MAX, ore_giornaliere))
    for data_g in giorni_ordinari:
        if not pom_slots:
            prob += pm[data_g] == 0
            continue
        pm_vars = [y[(data_g, h)] for h in pom_slots]
        for v in pm_vars:
            prob += pm[data_g] >= v
        prob += pm[data_g] <= pulp.lpSum(pm_vars)
    if pom_slots:
        for (anno, mese), giorni_mese in _giorni_per_mese(all_days).items():
            pm_mese = [pm[d] for d in giorni_mese if d in pm]
            if pm_mese:
                prob += pulp.lpSum(pm_mese) <= MAX_POMERIGGI_AL_MESE

    # ── 6) Obiettivo: massimizza ore piazzate, penalizza frammentazione ─
    all_x_vars = list(x.values())
    trans = []
    for data_g in giorni_ordinari:
        for h in range(ore_giornaliere - 1):
            t = pulp.LpVariable(f"t_{data_g}_{h}", 0, 1, pulp.LpBinary)
            trans.append(t)
            prob += t >= y[(data_g, h)] - y[(data_g, h + 1)]
            prob += t >= y[(data_g, h + 1)] - y[(data_g, h)]
    prob += pulp.lpSum(all_x_vars) - 0.001 * pulp.lpSum(trans)

    # ── 7) Risoluzione Fase 1 ──────────────────────────────────
    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    status = pulp.LpStatus[prob.status]
    print(f"[PuLP F1] {classe.nome_classe}: status={status}, "
          f"giorni_ordinari={len(giorni_ordinari)}, "
          f"slot_liberi={sum(1 for v in libero.values() if v)}")

    # ── 8) Applica risultato Fase 1 ────────────────────────────
    if status in ("Optimal", "Feasible"):
        for key, giorni in giorni_per_key.items():
            griglia = griglie[key]
            for g in giorni:
                data_g    = g["data"]
                giorno_it = g["giorno_it"]
                if bloccata[data_g]:
                    continue
                row = griglia[data_g]
                for h in range(ore_giornaliere):
                    if not libero.get((data_g, h), False):
                        continue
                    assegnata = None
                    for mid in materie_attive:
                        if (mid, data_g, h) in x and pulp.value(x[(mid, data_g, h)]) > 0.5:
                            assegnata = mid
                            break
                    if assegnata is None:
                        row[h] = None
                        continue
                    info_m       = materie_attive[assegnata]
                    docente_id   = info_m.get("docente_id")
                    docente_nome = info_m.get("docente_nome", "")
                    nome_materia = info_m["nome"]
                    if not docente_disponibile_global(
                        docente_id, data_g, h, giorno_it, docente_ok_wrapper
                    ):
                        print(f"[WARN] Docente {docente_id} non disponibile {data_g} h={h}, skip.")
                        row[h] = None
                        continue
                    piazza_blocco(
                        griglia, data_g, h, 1,
                        nome_materia, docente_nome, docente_id, None,
                        classe_id=classe.id,
                        materia_id=assegnata,
                        tipo="ORDINARIO_PULP",
                        origine="ordinario_pulp",
                    )
                    if docente_id:
                        occ.occupa(docente_id, classe.id, data_g, h)
                    info_m["debito_residuo"] = max(0, info_m.get("debito_residuo", 0) - 1)
                    info_m["ore_assegnate"]  = info_m.get("ore_assegnate", 0) + 1
    else:
        print(f"[WARN] PuLP F1 INFEASIBLE per {classe.nome_classe}. Si passa direttamente a Fase 2.")

    # Riepilogo Fase 1
    ore_f1 = sum(
        1 for key, giorni in giorni_per_key.items()
        for g in giorni if not bloccata[g["data"]]
        for h in range(ore_giornaliere)
        if isinstance(griglie[key][g["data"]][h], dict)
        and griglie[key][g["data"]][h].get("origine") == "ordinario_pulp"
    )
    debito_residuo_f1 = sum(i.get("debito_residuo", 0) for i in materie_attive.values())
    print(f"[PuLP F1] {classe.nome_classe}: ore piazzate={ore_f1}, debito_residuo={debito_residuo_f1}")

    # ── 9) Fase 2 — Greedy fallback ────────────────────────────
    if debito_residuo_f1 > 0:
        print(f"[GREEDY] {classe.nome_classe}: avvio Fase 2 per {debito_residuo_f1} ore residue...")
        _greedy_fallback(
            griglie,
            giorni_per_key,
            bloccata,
            libero,          # mappa originale degli slot liberi
            classe,
            materie_attive,
            ore_giornaliere,
            docente_ok_wrapper,
        )

    # Riepilogo finale
    ore_tot = sum(
        1 for key, giorni in giorni_per_key.items()
        for g in giorni if not bloccata[g["data"]]
        for h in range(ore_giornaliere)
        if isinstance(griglie[key][g["data"]][h], dict)
        and griglie[key][g["data"]][h].get("origine") in ("ordinario_pulp", "ordinario_greedy")
    )
    debito_finale = sum(i.get("debito_residuo", 0) for i in materie_attive.values())
    print(f"[FINALE] {classe.nome_classe}: ore_totali_piazzate={ore_tot}, "
          f"debito_non_piazzato={debito_finale}")
    if debito_finale > 0:
        print(f"[FINALE WARN] {classe.nome_classe}: {debito_finale} ore non piazzabili "
              f"(slot esauriti o docenti non disponibili in nessun giorno).")

    return griglie


# ──────────────────────────────────────────────────────────────
# UTILITY ESPOSTE
# ──────────────────────────────────────────────────────────────

def count_ore_docente_in_classe(docente_id, griglia_classe, data,
                                 ore_giornaliere=None):
    if not docente_id or data not in griglia_classe:
        return 0
    return sum(
        1 for s in griglia_classe[data]
        if isinstance(s, dict) and s.get("docente_id") == docente_id
    )


def crea_buco_docente(docente_id, data, ora):
    occ_doc       = occ.OCCUPAZIONE_DOCENTI_GLOBALE.get(docente_id, {})
    ore_impegnate = list(occ_doc.get(data, {}).keys())
    return (any(h < ora for h in ore_impegnate)
            and any(h > ora for h in ore_impegnate))


def registra_occupazione(*args, **kwargs):
    pass
