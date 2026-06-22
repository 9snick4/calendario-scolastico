from app.models import Festivita
import app.utils.occupazione as occ


def giorno_in_festivita(data):
    """
    Ritorna True se la data è dentro un periodo di festività del DB.
    """
    festivita = Festivita.query.all()
    for f in festivita:
        if f.data_inizio <= data <= f.data_fine:
            return True
    return False


def apply_festivita(griglia, giorni_settimana):
    """
    FESTIVITÀ (hard lock totale):
    - riempie la giornata con 'FESTA'
    - mantiene la griglia come dict {ora: slot}
    - registra occupazione globale come blocco speciale
    """

    for g in giorni_settimana:
        data_g = g["data"]

        if giorno_in_festivita(data_g):

            # Assicuriamoci che la griglia sia un dict
            row = griglia[data_g]
            if isinstance(row, list):
                row = {i: row[i] for i in range(len(row))}
                griglia[data_g] = row

            ore_giornaliere = len(row)

            # Riempie la giornata con blocchi FESTA
            for ora in range(ore_giornaliere):
                row[ora] = {
                    "materia": "FESTA",
                    "materia_id": None,
                    "docente": "",
                    "docente_id": None,
                    "fisso": True,
                    "tipo": "FESTA"
                }

            # 🔥 Registra occupazione globale nel formato corretto
            occ.OCCUPAZIONE_DOCENTI_GLOBALE.setdefault("FESTA", {})
            occ.OCCUPAZIONE_DOCENTI_GLOBALE["FESTA"].setdefault(data_g, {})

            for ora in range(ore_giornaliere):
                occ.OCCUPAZIONE_DOCENTI_GLOBALE["FESTA"][data_g][ora] = True
