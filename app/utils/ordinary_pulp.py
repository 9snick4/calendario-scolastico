from datetime import date
from collections import defaultdict

import pulp
from app.utils.orario_utils import piazza_blocco
import app.utils.occupazione as occ

CUTOFF_MARZO = (3, 1)


def ore_minime_giornata(data_g):
    cutoff = date(data_g.year, CUTOFF_MARZO[0], CUTOFF_MARZO[1])
    return 6 if data_g < cutoff else 4


def apply_ordinary_pulp(
    griglie,
    settimane_classe,
    classe,
    materie_info,
    materie_dict,
    docenti_dict,
    occupazione_docenti,
    docente_ok_wrapper,
):
    ore_giornaliere = classe.ore_massime_giornaliere or 6

    # 1) Indici giorni
    giorni_per_key = {}
    all_days = []
    for key in sorted(settimane_classe.keys()):
        giorni = sorted(settimane_classe[key], key=lambda x: x["data"])
        giorni_per_key[key] = giorni
        for g in giorni:
            all_days.append(g["data"])

    # 2) Slot fissi/speciali e ore già presenti
    fixed_slots = {}
    fixed_flag = {}
    giornata_speciale = {}
    ore_presenti = defaultdict(int)

    for key, giorni in giorni_per_key.items():
        griglia = griglie[key]
        for g in giorni:
            data_g = g["data"]
            row = griglia[data_g]
            spec = False
            for h in range(ore_giornaliere):
                s = row[h]
                if s is not None:
                    ore_presenti[data_g] += 1
                    if slot_e_fisso(s):
                        fixed_slots[(data_g, h)] = s
                        fixed_flag[(data_g, h)] = 1
                        spec = True
                    else:
                        fixed_flag[(data_g, h)] = 0
                else:
                    fixed_flag[(data_g, h)] = 0
            giornata_speciale[data_g] = spec or giornata_bloccata(row)

    # 3) Modello
    prob = pulp.LpProblem(f"Orario_{classe.nome_classe}", pulp.LpMinimize)

    x = {}    # x[mid, data, h] = 1 se materia mid in (data,h)
    y = {}    # y[data, h] = 1 se slot occupato (fisso o ordinario)
    z = {}    # z[mid, data, h] = 1 se blocco materia mid parte a h
    c = {}    # c[data, h] = 1 se da h a h+3 sono tutte occupate (4 consecutive)
    b = {}    # b[data, h] = 1 se buco 1-0-1
    iso = {}  # iso[data, h] = 1 se slot isolato

    materia_docente = {mid: info.get("docente_id") for mid, info in materie_info.items()}
    materia_blocco = {
        mid: max(info.get("blocco_orario", 1), info.get("ore_minime_consecutive", 1))
        for mid, info in materie_info.items()
    }

    # 4) Variabili
    for data_g in all_days:
        for h in range(ore_giornaliere):
            # y
            y[(data_g, h)] = pulp.LpVariable(
                f"y_{data_g}_{h}", 0, 1, pulp.LpBinary
            )
            if (data_g, h) in fixed_slots:
                prob += y[(data_g, h)] == 1

            # x
            for mid, info in materie_info.items():
                if info.get("debito_residuo", 0) <= 0:
                    continue
                x[(mid, data_g, h)] = pulp.LpVariable(
                    f"x_{mid}_{data_g}_{h}", 0, 1, pulp.LpBinary
                )
                if (data_g, h) in fixed_slots:
                    prob += x[(mid, data_g, h)] == 0

            # c (4 consecutive)
            if h <= ore_giornaliere - 4 and not giornata_speciale.get(data_g, False):
                c[(data_g, h)] = pulp.LpVariable(
                    f"c_{data_g}_{h}", 0, 1, pulp.LpBinary
                )

            # b (buco 1-0-1)
            if 0 < h < ore_giornaliere - 1 and not giornata_speciale.get(data_g, False):
                b[(data_g, h)] = pulp.LpVariable(
                    f"b_{data_g}_{h}", 0, 1, pulp.LpBinary
                )

            # iso (slot isolato)
            if not giornata_speciale.get(data_g, False):
                iso[(data_g, h)] = pulp.LpVariable(
                    f"iso_{data_g}_{h}", 0, 1, pulp.LpBinary
                )

        # z (blocchi)
        for mid, info in materie_info.items():
            if info.get("debito_residuo", 0) <= 0:
                continue
            L = materia_blocco[mid]
            for h in range(ore_giornaliere - L + 1):
                z[(mid, data_g, h)] = pulp.LpVariable(
                    f"z_{mid}_{data_g}_{h}", 0, 1, pulp.LpBinary
                )

    # 5) Vincoli

    # 5.1) Collegamento y con x e fissi: y = 1 se fisso o se c'è una materia
    for data_g in all_days:
        for h in range(ore_giornaliere):
            vars_slot = [x[(mid, data_g, h)]
                         for (mid, d, hh) in x.keys()
                         if d == data_g and hh == h]
            if vars_slot:
                # y >= somma x
                prob += y[(data_g, h)] >= pulp.lpSum(vars_slot)
                # y <= fixed_flag + somma x
                prob += y[(data_g, h)] <= fixed_flag[(data_g, h)] + pulp.lpSum(vars_slot)
            else:
                # se non ci sono x, y può essere solo fisso
                prob += y[(data_g, h)] <= fixed_flag[(data_g, h)]

    # 5.2) Un solo ordinario per slot
    for data_g in all_days:
        for h in range(ore_giornaliere):
            vars_slot = [x[(mid, data_g, h)]
                         for (mid, d, hh) in x.keys()
                         if d == data_g and hh == h]
            if vars_slot:
                prob += pulp.lpSum(vars_slot) <= (0 if (data_g, h) in fixed_slots else 1)

    # 5.3) Debito materia = somma ore singole + blocchi*L
    for mid, info in materie_info.items():
        debito = info.get("debito_residuo", 0)
        if debito <= 0:
            continue
        L = materia_blocco[mid]
        vars_x = [x[(mid, d, h)] for (m, d, h) in x.keys() if m == mid]
        vars_z = [z[(mid, d, h)] for (m, d, h) in z.keys() if m == mid]
        prob += pulp.lpSum(vars_x) + L * pulp.lpSum(vars_z) == debito

    # 5.4) Collegamento blocchi → ore
    for (mid, data_g, h0), varz in z.items():
        L = materia_blocco[mid]
        for k in range(L):
            prob += x[(mid, data_g, h0 + k)] >= varz

    # 5.5) Max 2 ore totali per docente per giornata
    for data_g in all_days:
        doc_to_vars = defaultdict(list)
        for (mid, d, h), var in x.items():
            if d != data_g:
                continue
            did = materia_docente.get(mid)
            if did:
                doc_to_vars[did].append(var)
        for did, vars_doc in doc_to_vars.items():
            prob += pulp.lpSum(vars_doc) <= 2

    # 5.6) Max 2 ore consecutive per docente
    for data_g in all_days:
        for h in range(ore_giornaliere - 2):
            doc_to_vars = defaultdict(list)
            for (mid, d, hh), var in x.items():
                if d != data_g:
                    continue
                if hh < h or hh > h + 2:
                    continue
                did = materia_docente.get(mid)
                if did:
                    doc_to_vars[did].append(var)
            for did, vars_doc in doc_to_vars.items():
                prob += pulp.lpSum(vars_doc) <= 2

    # 5.7) Minimo ore per giornata (su y)
    for data_g in all_days:
        if giornata_speciale.get(data_g, False):
            continue
        minimo = ore_minime_giornata(data_g)
        prob += pulp.lpSum([y[(data_g, h)] for h in range(ore_giornaliere)]) >= minimo

    # 5.8) Almeno 4 consecutive (su y)
    for data_g in all_days:
        if giornata_speciale.get(data_g, False):
            continue
        poss = []
        for h in range(ore_giornaliere - 3):
            if (data_g, h) not in c:
                continue
            poss.append(c[(data_g, h)])
            prob += c[(data_g, h)] <= y[(data_g, h)]
            prob += c[(data_g, h)] <= y[(data_g, h + 1)]
            prob += c[(data_g, h)] <= y[(data_g, h + 2)]
            prob += c[(data_g, h)] <= y[(data_g, h + 3)]
            prob += c[(data_g, h)] >= (
                y[(data_g, h)] + y[(data_g, h + 1)] +
                y[(data_g, h + 2)] + y[(data_g, h + 3)] - 3
            )
        if poss:
            prob += pulp.lpSum(poss) >= 1

    # 5.9) Vietare buchi 1-0-1 (HARD)
    for data_g in all_days:
        if giornata_speciale.get(data_g, False):
            continue
        for h in range(1, ore_giornaliere - 1):
            if (data_g, h) not in b:
                continue
            # b = 1 se pattern 1-0-1
            prob += b[(data_g, h)] >= y[(data_g, h - 1)] + y[(data_g, h + 1)] - 1
            prob += b[(data_g, h)] >= y[(data_g, h - 1)] - y[(data_g, h)]
            prob += b[(data_g, h)] >= y[(data_g, h + 1)] - y[(data_g, h)]
            prob += b[(data_g, h)] <= 1 - y[(data_g, h)]
            # HARD: vietiamo b
            prob += b[(data_g, h)] == 0

    # 5.10) No ore isolate: se y[h]=1 → almeno un vicino 1
    for data_g in all_days:
        if giornata_speciale.get(data_g, False):
            continue
        for h in range(ore_giornaliere):
            if (data_g, h) not in iso:
                continue
            left = y[(data_g, h - 1)] if h - 1 >= 0 else 0
            right = y[(data_g, h + 1)] if h + 1 < ore_giornaliere else 0
            # iso >= y[h] - (left + right)
            prob += iso[(data_g, h)] >= y[(data_g, h)] - (left + right)
            # iso <= y[h]
            prob += iso[(data_g, h)] <= y[(data_g, h)]
            # HARD: vietiamo iso
            prob += iso[(data_g, h)] == 0

    # 6) Obiettivo: minimizza transizioni (compattezza)
    trans = []
    for data_g in all_days:
        for h in range(ore_giornaliere - 1):
            t = pulp.LpVariable(f"t_{data_g}_{h}", 0, 1, pulp.LpBinary)
            trans.append(t)
            prob += t >= y[(data_g, h)] - y[(data_g, h + 1)]
            prob += t >= y[(data_g, h + 1)] - y[(data_g, h)]

    prob += pulp.lpSum(trans)

    # 7) Risolvi
    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    # 8) Applica risultato
    for key, giorni in giorni_per_key.items():
        griglia = griglie[key]
        for g in giorni:
            data_g = g["data"]
            giorno_it = g["giorno_it"]
            row = griglia[data_g]

            for h in range(ore_giornaliere):
                if (data_g, h) in fixed_slots:
                    continue

                assegnata = None
                for mid in materie_info:
                    if (mid, data_g, h) in x and pulp.value(x[(mid, data_g, h)]) > 0.5:
                        assegnata = mid
                        break

                if assegnata is None:
                    row[h] = None
                    continue

                info_m = materie_info[assegnata]
                docente_id = info_m.get("docente_id")
                docente_nome = info_m.get("docente_nome", "")
                nome_materia = info_m["nome"]

                if not docente_disponibile_global(
                    docente_id, data_g, h, giorno_it, docente_ok_wrapper
                ):
                    row[h] = None
                    continue

                piazza_blocco(
                    griglia,
                    data_g,
                    h,
                    1,
                    nome_materia,
                    docente_nome,
                    docente_id,
                    None,
                    classe_id=classe.id,
                    materia_id=assegnata,
                    tipo="ORDINARIO_PULP",
                    origine="ordinario_pulp",
                )

                if docente_id:
                    occ.occupa(docente_id, classe.id, data_g, h)

    return griglie
