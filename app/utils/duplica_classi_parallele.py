# app/utils/duplica_parallele.py

from copy import deepcopy

def duplica_classi_parallele(calendario, associazioni, doc_est_map):
    """
    Duplica SOLO le materie non professionali.
    Mantiene STAGE, FESTA e slot fissi.
    Non registra DOC EST nell’occupazione globale.
    """

    for classe_principale, classi_associate in associazioni.items():

        if classe_principale not in calendario:
            continue

        orario_principale = calendario[classe_principale]

        for classe_assoc in classi_associate:

            calendario[classe_assoc] = {}

            for data, ore in orario_principale.items():
                calendario[classe_assoc][data] = {}

                for ora, lezione in ore.items():

                    # 1️⃣ Copia STAGE / FESTA / FISSI senza modificarli
                    if lezione is None:
                        calendario[classe_assoc][data][ora] = None
                        continue

                    if lezione.get("tipo") in ("STAGE", "FESTA"):
                        calendario[classe_assoc][data][ora] = deepcopy(lezione)
                        continue

                    if lezione.get("fisso"):
                        calendario[classe_assoc][data][ora] = deepcopy(lezione)
                        continue

                    # 2️⃣ NON duplicare materie professionali
                    if lezione.get("tipo") == "PROFESSIONALE":
                        calendario[classe_assoc][data][ora] = None
                        continue

                    # 3️⃣ Duplica SOLO le materie non professionali
                    nuova = deepcopy(lezione)
                    nuova["docente"] = doc_est_map.get(classe_assoc, "DOC EST")
                    nuova["docente_id"] = None
                    nuova["origine"] = f"duplicata_da_{classe_principale}"

                    calendario[classe_assoc][data][ora] = nuova

    return calendario
