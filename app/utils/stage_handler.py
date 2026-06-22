# app/utils/stage_handler.py

import app.utils.occupazione as occ
from app.utils.orario_utils import classe_in_stage_giorno, giorno_festivo


def apply_stage(griglia, giorni_settimana, classe):
    """
    STAGE (hard lock totale):
    - riempie tutta la giornata con 'STAGE'
    - marca gli slot come fissi e non modificabili
    - registra l’occupazione della CLASSE (non del docente!)
    - impedisce al motore ordinario di usare questi slot
    """

    for g in giorni_settimana:
        data_g = g["data"]

        if giorno_festivo(data_g):
            continue

        if classe_in_stage_giorno(classe.id, data_g):

            row = griglia[data_g]          # SEMPRE list
            ore_giornaliere = len(row)

            for ora in range(ore_giornaliere):
                row[ora] = {
                    "materia": "STAGE",
                    "materia_id": None,
                    "docente": "",
                    "docente_id": None,
                    "classe_id": classe.id,
                    "fisso": True,
                    "tipo": "STAGE",
                    "origine": "stage",
                    "blocco": 1
                }

            occ.OCCUPAZIONE_CLASSI_GLOBALE.setdefault(classe.id, {})
            occ.OCCUPAZIONE_CLASSI_GLOBALE[classe.id].setdefault(data_g, {})

            for ora in range(ore_giornaliere):
                occ.OCCUPAZIONE_CLASSI_GLOBALE[classe.id][data_g][ora] = True
