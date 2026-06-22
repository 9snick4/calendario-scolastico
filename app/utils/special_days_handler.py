# app/utils/special_days_handler.py

from app.models import Docente, GiornoSpeciale
from app.utils.orario_utils import piazza_blocco
import app.utils.occupazione as occ
from app.utils.utils_scheduler import docente_ok_wrapper   # ✔ IMPORT CORRETTO
from collections import defaultdict


def apply_special_days(
    griglia,
    giorni_settimana,
    classe,
    materie_info,
    materie_dict,
    occupazione_docenti,
    docente_ok
):
    print(">>> APPLY SPECIAL DAYS INIZIATO")

    giorni_speciali = GiornoSpeciale.query.filter_by(classe_id=classe.id).all()

    # Raggruppa tutti i giorni speciali per data
    per_data = defaultdict(list)
    for gs in giorni_speciali:
        data_g = gs.data.date() if hasattr(gs.data, "date") else gs.data
        per_data[data_g].append(gs)

    for data_g, lista_gs in per_data.items():

        if data_g not in griglia:
            continue

        row = griglia[data_g]

        # Salta STAGE e FESTA
        if any(slot and isinstance(slot, dict) and
               slot.get("tipo") in ("STAGE", "FESTA")
               for slot in row):
            continue

        g = next((x for x in giorni_settimana if x["data"] == data_g), None)
        giorno_it = g["giorno_it"] if g else data_g.strftime("%A").upper()

        ore_giornaliere = len(row)

        print(f"\n[SPECIAL] === Giorno {data_g} ({giorno_it}) — {len(lista_gs)} materie da piazzare ===")
        print(f"[SPECIAL] Stato iniziale griglia: {[s.get('tipo') if isinstance(s, dict) else s for s in row]}")

        # Piazza tutte le materie speciali di questa giornata
        for gs in lista_gs:
            mid = next((k for k, v in materie_dict.items() if v == gs.materia), None)
            print(f"\n[SPECIAL] Provo: {gs.materia}, mid={mid}, docente_id={gs.docente_id}, ore_richieste={gs.ore}")

            if mid not in materie_info:
                print(f"[SPECIAL] SKIP: mid={mid} non trovato in materie_info.")
                continue

            info_m = materie_info[mid]
            docente_id = gs.docente_id
            docente = Docente.query.get(docente_id) if docente_id else None

            ore_da_piazzare = min(gs.ore, info_m["debito_residuo"])
            print(f"[SPECIAL] debito_residuo={info_m['debito_residuo']}, ore_da_piazzare={ore_da_piazzare}")

            if ore_da_piazzare <= 0:
                continue

            # Cerca il primo blocco consecutivo libero
            start = None
            for i in range(ore_giornaliere - ore_da_piazzare + 1):
                liberi = all(griglia[data_g][i + j] is None for j in range(ore_da_piazzare))
                if not liberi:
                    continue

                tutti_ok = True
                for j in range(ore_da_piazzare):
                    h = i + j

                    # ✔ docente_ok_wrapper con parametri corretti
                    ok_global = docente_ok_wrapper(docente_id, data_g, h, giorno_it, 1)

                    if not ok_global:
                        tutti_ok = False
                        break

                if tutti_ok:
                    start = i
                    break

            print(f"[SPECIAL] → start={start}")

            if start is None:
                print(f"[WARN] Nessun blocco consecutivo per {gs.materia} il {data_g}")
                continue

            # Piazza blocco speciale
            for j in range(ore_da_piazzare):
                h = start + j
                piazza_blocco(
                    griglia, data_g, h, 1,
                    gs.materia,
                    docente.nome_docente if docente else "",
                    docente_id, None,
                    classe_id=classe.id,
                    materia_id=mid,
                    tipo="SPECIALE",
                    origine="speciale"
                )

                slot = griglia[data_g][h]
                slot["fisso"] = True
                slot["tipo"] = "SPECIALE"
                slot["origine"] = "speciale"
                slot["speciale"] = True

                if docente_id:
                    occ.OCCUPAZIONE_DOCENTI_GLOBALE.setdefault(
                        docente_id, {}
                    ).setdefault(data_g, {})[h] = 1

            info_m["debito_residuo"] -= ore_da_piazzare
            info_m["ore_assegnate"] += ore_da_piazzare

            print(f"[SPECIAL] ✓ Piazzato {gs.materia} ore {start}-{start + ore_da_piazzare - 1}")
            print(f"[SPECIAL] Griglia dopo: {[s.get('tipo') if isinstance(s, dict) else s for s in griglia[data_g]]}")

        # Blocca gli slot vuoti rimanenti come SPECIALI_VUOTO
        for i in range(ore_giornaliere):
            if griglia[data_g][i] is None:
                griglia[data_g][i] = {
                    "materia": "",
                    "materia_id": None,
                    "docente": "",
                    "docente_id": None,
                    "fisso": True,
                    "tipo": "SPECIALE_VUOTO",
                    "origine": "speciale",
                    "speciale": True,
                }

        print(f"[SPECIAL] Griglia finale {data_g}: {[s.get('tipo') if isinstance(s, dict) else s for s in griglia[data_g]]}")
