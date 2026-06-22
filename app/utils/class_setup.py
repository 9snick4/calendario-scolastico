# app/utils/class_setup.py

from datetime import timedelta
from collections import defaultdict

from app.models import (
    Classe,
    MateriaClasse,
    Materia,
    AnnoFormativo,
    GiornoFisso,
    Docente
)

from app.utils.orario_utils import (
    normalizza_giorno_it,
    label_giorno_it
)

# 🔥 IMPORTA L’UNICA OCCUPAZIONE GLOBALE
import app.utils.occupazione as occ


def prepara_classi():
    """
    Prepara tutte le strutture dati necessarie al motore:
    - classi_info
    - materie_info
    - settimane per classe
    - dizionari docenti/materie
    - occupazione docenti LOCALE (separata dalla globale)
    """

    anno = AnnoFormativo.query.first()
    if not anno:
        return {}, [], {}, {}, set(), {}

    # Dizionari base
    classi = Classe.query.order_by(Classe.nome_classe).all()
    materie = Materia.query.all()
    materie_dict = {m.id: m.nome for m in materie}
    docenti_dict = {d.id: d.nome_docente for d in Docente.query.all()}
    nomi_non_prof = {m.nome for m in materie if not m.is_professionale}

    # 🔥 Reset SOLO la globale (usata da docente_ok_wrapper / registra_occupazione)
    occ.OCCUPAZIONE_DOCENTI_GLOBALE.clear()
    print("RESET OCCUPAZIONE GLOBALE")

    # 🔥 occupazione_docenti DEVE ESSERE INDIPENDENTE, basata su set
    #    NON deve mai puntare alla globale
    occupazione_docenti = defaultdict(lambda: defaultdict(set))

    classi_info = {}

    # ------------------------------------------------------------
    # COSTRUZIONE STRUTTURE PER OGNI CLASSE
    # ------------------------------------------------------------

    for classe in classi:

        # Giorni di lezione
        if classe.giorni_lezione:
            giorni_lezione = [
                normalizza_giorno_it(g)
                for g in classe.giorni_lezione.split(",")
                if g.strip()
            ]
        else:
            giorni_lezione = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]

        ore_giornaliere = classe.ore_massime_giornaliere or 6
        data_inizio = classe.data_inizio or anno.data_inizio
        data_fine = classe.data_fine or anno.data_fine

        # ------------------------------------------------------------
        # COSTRUZIONE LISTA GIORNI DI LEZIONE
        # ------------------------------------------------------------

        giorni_classe = []
        current = data_inizio

        while current <= data_fine:
            giorno_it = normalizza_giorno_it(label_giorno_it(current))
            if giorno_it in giorni_lezione:
                iso_year, iso_week, _ = current.isocalendar()
                giorni_classe.append({
                    "data": current,
                    "giorno_it": giorno_it,
                    "iso_year": iso_year,
                    "iso_week": iso_week,
                })
            current += timedelta(days=1)

        # ------------------------------------------------------------
        # RAGGRUPPAMENTO PER SETTIMANA
        # ------------------------------------------------------------

        settimane_classe = {}
        for g in giorni_classe:
            key = (g["iso_year"], g["iso_week"])
            settimane_classe.setdefault(key, []).append(g)

        # ------------------------------------------------------------
        # MATERIE DELLA CLASSE
        # ------------------------------------------------------------

        materie_classe = MateriaClasse.query.filter_by(classe_id=classe.id).all()

        # Ore fisse (giorni fissi)
        ore_fisse_per_materia = {}
        giorni_fissi_classe = GiornoFisso.query.filter_by(classe_id=classe.id).all()

        for gf in giorni_fissi_classe:
            ore_fisse_per_materia.setdefault(gf.materia_id, 0)
            ore_fisse_per_materia[gf.materia_id] += gf.ore

        # ------------------------------------------------------------
        # COSTRUZIONE MATERIE_INFO
        # ------------------------------------------------------------

        num_settimane = len(settimane_classe) or 1
        materie_info = {}

        for mc in materie_classe:
            ore_annuali = mc.ore_annuali or 0
            if ore_annuali <= 0:
                continue

            # Ore settimanali teoriche
            ore_sett_teoriche = max(1, round(ore_annuali / num_settimane))

            # Ore fisse già assegnate
            ore_fisse = ore_fisse_per_materia.get(mc.materia_id, 0)

            # Ore libere da piazzare
            ore_libere_sett = max(0, ore_sett_teoriche - ore_fisse)

            materie_info[mc.materia_id] = {
                "id": mc.materia_id,
                "nome": materie_dict.get(mc.materia_id, "Materia"),
                "docente_id": mc.docente_id,
                "ore_annuali": ore_annuali,                 # ⭐ AGGIUNTO
                "ore_annuali_totali": ore_annuali,
                "ore_settimanali_teoriche": ore_libere_sett,
                "ore_fisse": ore_fisse,
                "ore_assegnate": 0,
                "debito_residuo": ore_annuali,
                "ore_minime_consecutive": mc.ore_minime_consecutive or 1,
            }


        # ------------------------------------------------------------
        # SALVATAGGIO STRUTTURA CLASSE
        # ------------------------------------------------------------

        classi_info[classe.id] = {
            "classe": classe,
            "ore_giornaliere": ore_giornaliere,
            "giorni_classe": giorni_classe,
            "settimane_classe": settimane_classe,
            "materie_info": materie_info,
            "giorni_fissi": giorni_fissi_classe,
            "calendario": [],
        }

    return (
        classi_info,
        classi,
        materie_dict,
        docenti_dict,
        nomi_non_prof,
        occupazione_docenti
    )
