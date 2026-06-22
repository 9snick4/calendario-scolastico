# app/utils/ordinary_placement.py
from datetime import date, datetime
from app.utils.orario_utils import piazza_blocco
import app.utils.occupazione as occ

# ──────────────────────────────────────────────────────────────
# CONFIGURAZIONE
# ──────────────────────────────────────────────────────────────
MAX_ORE_DOCENTE_PER_GIORNO = 2 

def get_minimo_ore(data_g):
    if not isinstance(data_g, date):
        data_g = datetime.strptime(data_g, "%Y-%m-%d").date()
    return 6 if data_g < date(data_g.year, 3, 1) else 4

# ──────────────────────────────────────────────────────────────
# CONTROLLO DISPONIBILITÀ GLOBALE (Fix per sovrapposizioni)
# ──────────────────────────────────────────────────────────────

def docente_disponibile_global(docente_id, data, ora, giorno_it=None, docente_ok=None):
    """
    Verifica se il docente è LIBERO in tutto l'istituto.
    Viene chiamata anche da special_days_handler e optimizer.
    """
    if not docente_id or docente_id == "DOC EST": 
        return True
        
    # 1. Verifica sovrapposizioni in altre classi
    if not occ.docente_libero(docente_id, data, ora): 
        return False
    
    # 2. Verifica desiderata (se forniti)
    if docente_ok:
        if not giorno_it:
            dt = data if isinstance(data, (date, datetime)) else datetime.strptime(data, "%Y-%m-%d")
            giorno_it = dt.strftime('%A')
        if not docente_ok(docente_id, data, giorno_it, ora, 1): 
            return False
            
    return True

# ──────────────────────────────────────────────────────────────
# VALIDAZIONE INSERIMENTO
# ──────────────────────────────────────────────────────────────

def valida_inserimento(docente_id, materia_id, data_dest, ora_dest, n_ore, 
                      griglia_dest, classe_id, docente_ok, materie_info):
    row_dest = griglia_dest[data_dest]
    giorno_it = data_dest.strftime('%A') 

    for h in range(ora_dest, ora_dest + n_ore):
        if h >= len(row_dest) or row_dest[h] is not None: return False
        
        # Controllo incrociato: il docente è libero in altre classi?
        if not docente_disponibile_global(docente_id, data_dest, h, giorno_it, docente_ok):
            return False
            
        if occ.classe_occupata(classe_id, data_dest, h): return False

    if docente_id:
        # Conta ore già fatte in questa classe oggi
        ore_gia = sum(1 for s in row_dest if isinstance(s, dict) and s.get("docente_id") == docente_id)
        if ore_gia + n_ore > MAX_ORE_DOCENTE_PER_GIORNO: return False
        
    return True

# ──────────────────────────────────────────────────────────────
# MOTORE DI GENERAZIONE (Fix KeyError)
# ──────────────────────────────────────────────────────────────

def esegui_generazione_compatta(griglie, settimane_classe, classe, materie_info, docente_ok):
    ore_max_g = classe.ore_massime_giornaliere or 6
    timeline = []
    for key in sorted(settimane_classe.keys()):
        for g in sorted(settimane_classe[key], key=lambda x: x["data"]):
            timeline.append((key, g["data"]))

    for key, data_g in timeline:
        row = griglie[key][data_g]
        if any(s and s.get("tipo") in ("STAGE", "FESTA") for s in row): continue
        target = get_minimo_ore(data_g)
        
        tentativi = 0
        while sum(1 for s in row if s is not None) < target and tentativi < 10:
            tentativi += 1
            
            # PREPARAZIONE CANDIDATI (Risolve il KeyError: 'materia_id')
            candidati = []
            for mid, info in materie_info.items():
                if info.get('debito_residuo', 0) > 0:
                    candidati.append((mid, info))
            
            # Priorità a chi ha più debito
            candidati.sort(key=lambda x: x[1]['debito_residuo'], reverse=True)
            
            piazzato_nel_ciclo = False
            for mid, info in candidati:
                did = info.get("docente_id")
                # Quante ore servono per arrivare al target?
                n_richieste = min(info["debito_residuo"], info.get("blocco_orario", 1), target - sum(1 for s in row if s is not None))
                
                # Cerchiamo il primo slot libero (consecutive)
                for start in range(ore_max_g - n_richieste + 1):
                    if valida_inserimento(did, mid, data_g, start, n_richieste, 
                                         griglie[key], classe.id, docente_ok, materie_info):
                        piazza_blocco(griglie[key], data_g, start, n_richieste, info["nome"], info.get("docente_nome", ""),
                                     did, None, classe_id=classe.id, materia_id=mid,
                                     tipo="ORDINARIO", origine="ordinario")
                        
                        # OCCUPA NEL REGISTRO GLOBALE ISTANTANEAMENTE
                        for h in range(start, start + n_richieste):
                            if did: occ.occupa(did, classe.id, data_g, h)
                        
                        info["debito_residuo"] -= n_richieste
                        info["ore_assegnate"] += n_richieste
                        piazzato_nel_ciclo = True
                        break
                if piazzato_nel_ciclo: break
            if not piazzato_nel_ciclo: break

# ──────────────────────────────────────────────────────────────
# PULIZIA FINALE (Compatta senza sovrapporre)
# ──────────────────────────────────────────────────────────────

def final_cleanup_safe(griglie, ore_max, materie_info, classe_id):
    """Sposta le ore in alto ma controlla che il docente sia libero nella nuova posizione."""
    for key in griglie:
        for data in list(griglie[key].keys()):
            row = griglie[key][data]
            if not row or any(s and s.get("tipo") in ("STAGE", "FESTA") for s in row): continue
            
            target = get_minimo_ore(data)
            ore_presenti = [s for s in row if s is not None]
            
            if not ore_presenti: continue

            # Se < target, svuota e restituisci debito (solo se non è fine anno)
            if len(ore_presenti) < target and sum(m["debito_residuo"] for m in materie_info.values()) > 0:
                if not any(s and s.get("fisso") for s in row):
                    for h, s in enumerate(row):
                        if s and not s.get("fisso"):
                            if s.get("docente_id"): occ.libera(s["docente_id"], data, h)
                            mid = s.get("materia_id")
                            if mid in materie_info:
                                materie_info[mid]["debito_residuo"] += 1
                                materie_info[mid]["ore_assegnate"] -= 1
                            row[h] = None
                    continue

            # Compattazione protetta
            for h, s in enumerate(row):
                if s and s.get("docente_id"): occ.libera(s["docente_id"], data, h)
            
            nuova_row = [None] * ore_max
            pos = 0
            for s in ore_presenti:
                did = s.get("docente_id")
                # Verifica se può stare nella posizione 'pos'
                if docente_disponibile_global(did, data, pos):
                    nuova_row[pos] = s
                    if did: occ.occupa(did, classe_id, data, pos)
                    pos += 1
                else:
                    # Se occupato altrove, cerca il primo buco successivo
                    for h_alt in range(pos + 1, ore_max):
                        if docente_disponibile_global(did, data, h_alt):
                            nuova_row[h_alt] = s
                            if did: occ.occupa(did, classe_id, data, h_alt)
                            break
            griglie[key][data] = nuova_row

# ──────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────

def apply_ordinary(griglie, settimane_classe, classe, materie_info, materie_dict, 
                   docenti_dict, occupazione_docenti, docente_ok):
    
    ore_max = classe.ore_massime_giornaliere or 6
    
    # 1. Init e caricamento occupazioni esistenti (da special days)
    for key in settimane_classe:
        for data in griglie[key]:
            if isinstance(griglie[key][data], dict):
                griglie[key][data] = [griglie[key][data].get(i) for i in range(ore_max)]
            occ.OCCUPAZIONE_CLASSI_GLOBALE.setdefault(classe.id, {}).setdefault(data, set())

    # Registra ore da special days/altre classi
    for did, giorni in occupazione_docenti.items():
        for d, ore_list in giorni.items():
            for h in ore_list:
                occ.occupa(did, None, d, h)

    # 2. Generazione
    esegui_generazione_compatta(griglie, settimane_classe, classe, materie_info, docente_ok)

    # 3. Cleanup e compattazione
    final_cleanup_safe(griglie, ore_max, materie_info, classe.id)

    return griglie

def count_ore_docente_in_classe(docente_id, griglia_classe, data, ore_giornaliere=None):
    if not docente_id or data not in griglia_classe: return 0
    return sum(1 for s in griglia_classe[data] if isinstance(s, dict) and s.get("docente_id") == docente_id)

def crea_buco_docente(docente_id, data, ora):
    occ_doc = occ.OCCUPAZIONE_DOCENTI_GLOBALE.get(docente_id, {})
    ore_impegnate = list(occ_doc.get(data, {}).keys())
    return any(h < ora for h in ore_impegnate) and any(h > ora for h in ore_impegnate)

def registra_occupazione(*args, **kwargs): pass