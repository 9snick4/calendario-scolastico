# app/utils/calendario_generator.py

from .class_setup import prepara_classi
from .stage_handler import apply_stage
from app.utils.festivita_handler import apply_festivita
from .special_days_handler import apply_special_days
from .fixed_days_handler import apply_fixed_days




from app.utils.orario_utils import (
    crea_griglia_settimanale,
    costruisci_settimana,
    salva_calendari,
    sincronizza_classi_associate
)

from app.utils.utils_scheduler import (
    docente_ok_wrapper,
)

from app.utils.ordinary_placement import (
    prepara_classi_data,
    _fase1_cpsat,
    _applica_cpsat,
    _greedy_fallback,
    _analizza_slot
)


import app.utils.occupazione as occ

print(">>> VERSIONE PATCHATA DEFINITIVA")


def genera_calendario_annuale():

    # 🔹 0) PULISCI OCCUPAZIONE GLOBALE UNA VOLTA SOLA
    occ.OCCUPAZIONE_DOCENTI_GLOBALE.clear()

    (
        classi_info,
        classi,
        materie_dict,
        docenti_dict,
        nomi_non_prof,
        occupazione_docenti
    ) = prepara_classi()

    # 🔹 strutture per validatore globale
    tutte_le_griglie = {}
    tutte_le_settimane = {}
    ore_giornaliere_max = 0

    # 1) COSTRUISCI GRIGLIE + SPECIALI/FISSI PER TUTTE LE CLASSI
    for cid, info in classi_info.items():

        classe = info["classe"]
        settimane_classe = info["settimane_classe"]
        ore_giornaliere = info["ore_giornaliere"]
        materie_info = info["materie_info"]
        giorni_fissi_classe = info["giorni_fissi"]

        ore_giornaliere_max = max(ore_giornaliere_max, ore_giornaliere)

        # Ogni classe deve avere un calendario indipendente
        calendario = []
        info["calendario"] = calendario

        # 1a) CREA GRIGLIE VUOTE
        griglie = {}
        for key in sorted(settimane_classe.keys()):
            giorni_settimana = sorted(settimane_classe[key], key=lambda x: x["data"])
            griglie[key] = crea_griglia_settimanale(giorni_settimana, ore_giornaliere)

        # 1b) STAGE, FESTIVITÀ, SPECIALI, FISSI
        for key in sorted(settimane_classe.keys()):
            giorni_settimana = sorted(settimane_classe[key], key=lambda x: x["data"])

            apply_stage(griglie[key], giorni_settimana, classe)
            apply_festivita(griglie[key], giorni_settimana)

            apply_special_days(
                griglie[key],
                giorni_settimana,
                classe,
                materie_info,
                materie_dict,
                occupazione_docenti,
                docente_ok_wrapper
            )

            apply_fixed_days(
                griglie[key],
                giorni_settimana,
                classe,
                materie_info,
                materie_dict,
                occupazione_docenti,
                giorni_fissi_classe,
                docente_ok_wrapper
            )

        # 1c) SALVA GRIGLIE NELLA STRUTTURA DELLA CLASSE
        info["griglie"] = griglie

        # 1d) ACCUMULA PER VALIDATORE GLOBALE
        tutte_le_griglie[cid] = griglie
        tutte_le_settimane[cid] = settimane_classe

    def piazzamento_ordinario(classi_info, docente_ok_wrapper):
        # 1) Prepara classi_data come fa oggi apply_ordinary_global
        classi_data = prepara_classi_data(classi_info)

        for cd in classi_data:
            cd["libero_originale"] = dict(cd["libero"])


        # 2) Primo passaggio: solo materie con blocchi >= 2
        x_vals_long = _fase1_cpsat(classi_data, docente_ok_wrapper,
                                filtro_materia=lambda info: info.get("ore_minime_consecutive",1) >= 2)
        if x_vals_long:
            for cd in classi_data:
                _applica_cpsat(cd, x_vals_long, docente_ok_wrapper)

        # 3) Ricalcola slot liberi dopo il primo passaggio
        for cd in classi_data:
            (cd["giorni_per_key"],
            cd["all_days"],
            cd["giorni_ordinari"],
            cd["libero"],
            cd["fissi_per_giorno"],
            cd["giorno_it_map"]) = _analizza_slot(cd["griglie"],
                                                cd["settimane_classe"],
                                                cd["ore_g"])

        # 4) Secondo passaggio: tutte le materie rimanenti
        x_vals_rest = _fase1_cpsat(classi_data, docente_ok_wrapper,
                                filtro_materia=lambda info: info.get("debito_residuo",0) > 0)
        if x_vals_rest:
            for cd in classi_data:
                _applica_cpsat(cd, x_vals_rest, docente_ok_wrapper)

        # 5) Greedy finale
        for cd in classi_data:
            _greedy_fallback(cd, docente_ok_wrapper)

    
    
    # 2) ORDINARIO — CP-SAT GLOBALE SU TUTTE LE CLASSI (UNA SOLA VOLTA)
    piazzamento_ordinario(classi_info, docente_ok_wrapper)


    # 3) COSTRUISCI SETTIMANE FINALI (CALENDARIO VERO) PER OGNI CLASSE
    for cid, info in classi_info.items():
        classe = info["classe"]
        settimane_classe = info["settimane_classe"]
        ore_giornaliere = info["ore_giornaliere"]
        calendario = info["calendario"]
        griglie = info["griglie"]

        for key in sorted(settimane_classe.keys()):
            if key not in griglie or griglie[key] is None:
                print(f"[WARN] griglie[{key}] è None per la classe {classe.nome_classe}, salto costruisci_settimana.")
                continue

            giorni_settimana = sorted(settimane_classe[key], key=lambda x: x["data"])
            costruisci_settimana(
                griglie[key],
                giorni_settimana,
                ore_giornaliere,
                calendario
            )

    # 4) CALENDARIO FINALE
    calendario_per_classe = salva_calendari(classi_info)

    # 5) DUPLICAZIONE PARALLELE (ancora opzionale/commentata)
    from app.utils.associazioni_loader import carica_associazioni_parallele, genera_doc_est_map
    associazioni = carica_associazioni_parallele()
    doc_est_map = genera_doc_est_map(associazioni)

    from app.utils.duplica_classi_parallele import duplica_classi_parallele

    # if associazioni:
    #     calendario_per_classe = duplica_classi_parallele(
    #         calendario_per_classe,
    #         associazioni,
    #         doc_est_map
    #     )

    # 6) VALIDATORE: cache per pagina diagnostica
    from app.utils.validator import set_validator_cache, valida_motore
    set_validator_cache(calendario_per_classe, classi_info)

    # 7) VALIDAZIONE MOTORE SU TUTTE LE CLASSI (UNA ALLA VOLTA)
    errori = []
    for cid, info in classi_info.items():
        griglie_classe = info.get("griglie")
        settimane_classe = info["settimane_classe"]
        ore_giornaliere = info["ore_giornaliere"]

        if not griglie_classe:
            continue

        err_classe = valida_motore(
            griglie_classe,
            settimane_classe,
            ore_giornaliere
        )
        nome = info["classe"].nome_classe
        errori.extend([f"[{nome}] {e}" for e in err_classe])

    if errori:
        print("\n=== ERRORI TROVATI ===")
        for e in errori:
            print(e)
    else:
        print("\n=== TUTTO COERENTE ===")

    return calendario_per_classe
