# app/utils/fixed_days_handler.py

from app.utils.orario_utils import piazza_blocco, normalizza_giorno_it
from app.models import Docente
import app.utils.occupazione as occ
from app.utils.utils_scheduler import docente_ok_wrapper  # ✔ usiamo il wrapper unico

print(">>> FIXED DAYS HANDLER CARICATO")


def apply_fixed_days(
    griglia,
    giorni_settimana,
    classe,
    materie_info,
    materie_dict,
    occupazione_docenti,
    giorni_fissi_classe,
    docente_ok
):
    if not giorni_fissi_classe:
        return

    for gf in giorni_fissi_classe:
        materia_id = gf.materia_id
        docente_id = gf.docente_id
        giorno_nome = gf.giorno
        ore_richieste = gf.ore

        if materia_id not in materie_info:
            continue

        info_m = materie_info[materia_id]
        docente = Docente.query.get(docente_id)

        if not docente:
            print(f"[ATTENZIONE] Giorno fisso senza docente valido: materia {materia_id}")
            continue

        for g in giorni_settimana:
            if normalizza_giorno_it(g["giorno_it"]) != normalizza_giorno_it(giorno_nome):
                continue

            data_g = g["data"]
            giorno_it = g["giorno_it"]
            row = griglia[data_g]

            # Non invadere giorni speciali dichiarati per quella materia
            if "giorni_speciali" in info_m and data_g in info_m["giorni_speciali"]:
                continue

            # Non invadere STAGE
            if any(slot and isinstance(slot, dict) and slot.get("tipo") == "STAGE"
                   for slot in row):
                continue

            # Non invadere FESTA
            if any(slot and isinstance(slot, dict) and slot.get("tipo") == "FESTA"
                   for slot in row):
                continue

            # Non invadere giorni già completamente occupati da FISSO/SPECIALE
            # (se c'è già qualcosa di fisso/speciale, saltiamo questo giorno per questa materia)
            if any(
                slot and isinstance(slot, dict) and (
                    slot.get("fisso") or slot.get("tipo") in ("FISSO", "SPECIALE")
                )
                for slot in row
            ):
                continue

            ore_giornaliere = len(row)
            ore_da_piazzare = min(ore_richieste, info_m["debito_residuo"], ore_giornaliere)

            if ore_da_piazzare <= 0:
                continue

            # Cerca il primo blocco CONSECUTIVO libero di ore_da_piazzare slot
            start = None
            for i in range(ore_giornaliere - ore_da_piazzare + 1):
                # Tutti gli slot del blocco devono essere liberi
                if not all(row[i + j] is None for j in range(ore_da_piazzare)):
                    continue

                # Tutti gli slot devono essere compatibili col docente (wrapper globale)
                tutti_ok = True
                for j in range(ore_da_piazzare):
                    h = i + j
                    if not docente_ok_wrapper(docente_id, data_g, h, giorno_it, 1):
                        tutti_ok = False
                        break

                if tutti_ok:
                    start = i
                    break

            if start is None:
                print(f"[WARN] Nessun blocco consecutivo per fisso materia {materia_id} il {data_g}")
                continue

            # Piazza le ore consecutive a partire da start
            for j in range(ore_da_piazzare):
                h = start + j

                piazza_blocco(
                    griglia,
                    data_g,
                    h,
                    1,
                    materie_dict[materia_id],
                    docente.nome_docente if docente else "",
                    docente_id,
                    occupazione_docenti,
                    classe_id=classe.id,
                    materia_id=materia_id,
                    tipo="FISSO",
                    origine="fisso"
                )

                occ.occupa(docente_id, classe.id, data_g, h)
                griglia[data_g][h]["fisso"] = True
                griglia[data_g][h]["origine"] = "fisso"
                griglia[data_g][h]["tipo"] = "FISSO"

            info_m["debito_residuo"] -= ore_da_piazzare
            info_m["ore_assegnate"] += ore_da_piazzare
