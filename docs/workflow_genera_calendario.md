# Workflow: Generazione del Calendario Scolastico

> **Entry point:** `POST /orario/genera` → `orario.py::genera_calendario()`  
> **Funzione principale:** `app/utils/calendario_generator.py::genera_calendario_annuale()`

---

## Panoramica

```
POST /orario/genera
    └── genera_calendario_annuale()
            ├── 0. Reset occupazioni globali
            ├── 1. prepara_classi()              → class_setup.py
            ├── 2. crea griglie settimanali vuote → orario_utils.crea_griglia_settimanale()
            ├── 3. Per ogni settimana, per ogni classe:
            │       ├── apply_stage()            → stage_handler.py
            │       ├── apply_festivita()        → festivita_handler.py
            │       ├── apply_special_days()     → special_days_handler.py
            │       └── apply_fixed_days()       → fixed_days_handler.py
            ├── 4. piazzamento_ordinario()       → ordinary_placement.py + fasi 5-8
            ├── 5. costruisci_settimana()        → orario_utils.py
            ├── 6. salva_calendari()             → orario_utils.py
            └── 7. valida_motore() + set_validator_cache()  → validator.py
    └── Costruisce Excel con openpyxl (un foglio per classe)
    └── Salva su disco in generated_calendars/calendario_TIMESTAMP.xlsx
    └── redirect → lista_versioni
```

---

## Fase 0 — Reset Occupazioni Globali

**File:** `calendario_generator.py`

Prima di tutto vengono azzerati i dizionari globali che tracciano chi è occupato dove:

```python
occ.OCCUPAZIONE_DOCENTI_GLOBALE.clear()
occ.OCCUPAZIONE_CLASSI_GLOBALE.clear()
```

Questo garantisce che una rigenerazione parta sempre da zero, senza residui di run precedenti.

---

## Fase 1 — `prepara_classi()` → `class_setup.py`

Carica tutte le strutture dati dal database e costruisce il dizionario `classi_info`.

Per ogni classe:

1. **Legge i giorni di lezione** (es. Lun-Ven). Default se non configurati.
2. **Itera ogni giorno** dal `data_inizio` al `data_fine` (dalla classe, o dall'`AnnoFormativo`).
3. **Raggruppa per settimana ISO** → `settimane_classe[(anno_iso, settimana_iso)]`.
4. **Per ogni `MateriaClasse`** calcola:
   - `ore_sett_teoriche = round(ore_annuali / num_settimane)`
   - `ore_fisse = sum` dei `GiornoFisso` per quella materia
   - `ore_libere_sett = ore_sett_teoriche - ore_fisse`
   - `debito_residuo = ore_annuali` (tutte le ore ancora da piazzare)

**Output:** `classi_info` — dizionario `classe_id → {classe, ore_giornaliere, giorni_classe, settimane_classe, materie_info, giorni_fissi, calendario}`

**Corner case:** se `AnnoFormativo` non esiste nel DB → restituisce strutture vuote, il calendario sarà vuoto.

---

## Fase 2 — Creazione Griglie Settimanali Vuote

**File:** `orario_utils.py::crea_griglia_settimanale()`

Per ogni settimana di ogni classe viene creata una griglia:

```
griglia[data] = [None, None, None, None, None, None]  # tanti None quante ore_giornaliere
```

Ogni `None` rappresenta uno slot orario ancora libero (da riempire nelle fasi successive).

---

## Fase 3a — `apply_stage()` → `stage_handler.py`

**Hard lock totale** per i giorni di stage.

- Controlla se il giorno rientra nel periodo di stage della classe (via `orario_utils.classe_in_stage_giorno()`).
- I giorni festivi hanno **priorità**: se festivo → salta.
- Per ogni ora della giornata, scrive:
  ```python
  {"materia": "STAGE", "fisso": True, "tipo": "STAGE", "origine": "stage"}
  ```
- Registra l'occupazione in `OCCUPAZIONE_CLASSI_GLOBALE`.

Dopo questa fase, quei slot **non possono essere modificati** dalle fasi successive.

---

## Fase 3b — `apply_festivita()` → `festivita_handler.py`

**Hard lock totale** per i giorni festivi (nazionali/locali da DB `Festivita`).

- Per ogni giorno che cade in un range `data_inizio`–`data_fine` di una festività:
  ```python
  {"materia": "FESTA", "fisso": True, "tipo": "FESTA"}
  ```
- Registra occupazione in `OCCUPAZIONE_DOCENTI_GLOBALE["FESTA"]`.

---

## Fase 3c — `apply_special_days()` → `special_days_handler.py`

**Giorni speciali** = giorni con ore ridotte (es. giornata di orientamento, uscite didattiche).

- Riempie solo i primi `N` slot della giornata con `"BLOCCO_SPECIALE"`.
- Gli slot oltre `N` vengono bloccati come non utilizzabili.
- Marca gli slot con `"origine": "speciale"` → intoccabili dalle fasi di ribilanciamento.

---

## Fase 3d — `apply_fixed_days()` → `fixed_days_handler.py`

**Giorni fissi** = materie che devono apparire in un giorno specifico della settimana.

- Per ogni `GiornoFisso` (es. "Educazione Fisica il Mercoledì, 2 ore"):
  - Trova i mercoledì della settimana corrente.
  - Piazza le ore richieste, verificando disponibilità docente via `docente_ok_wrapper()`.
  - Marca gli slot con `"origine": "fisso"` → intoccabili dalle fasi di ribilanciamento.

---

## Fase 4 — `piazzamento_ordinario()` + Ciclo di Ribilanciamento

**File:** `ordinary_placement.py` + fasi 5-8 in `calendario_generator.py`

### 4a — Setup Pre-Motore

Per ogni classe (`cd` = "classe data"):
- Costruisce `tipo_giorno` (STAGE/FESTA/SPECIALE/normale per ogni data).
- Costruisce i set `fissi_per_giorno` e `speciali_per_giorno` (slot intoccabili).
- Salva `libero_originale` (snapshot degli slot liberi prima del motore).

### 4b — `ordinary_placement()` → `ordinary_placement.py`

Il motore principale. Scansiona settimana per settimana, per ogni materia con `debito_residuo > 0`:
- Cerca slot liberi.
- Verifica disponibilità docente (`docente_ok_wrapper()` + `occ.docente_libero()`).
- Rispetta `ore_minime_consecutive` (es. "Matematica sempre in blocchi di 2 ore").
- Piazza l'ora e aggiorna `debito_residuo`.

### 4c — Ciclo di Ribilanciamento (max `MAX_ITER = 5` volte)

Dopo il motore ordinario, se rimane `debito_residuo > 0` su qualche materia, partono le fasi di recupero. Il ciclo si ferma se nessuna fase produce cambiamenti.

| Fase | Funzione | Cosa fa |
|------|----------|---------|
| **5** | `fallback_riempimento_buchi()` | Riempie slot vuoti rimasti. Priorità alle date più lontane. |
| **6** | `fase6_ribilanciamento()` | Intra-classe: sposta materie leggere (debito=0, ore_minime=1) per fare spazio a materie critiche. |
| **7** | `fase7_ribilanciamento_interclassi()` | Inter-classi: se un docente insegna in più classi, libera un'ora da una classe senza debito per cederla a una con debito. |
| **8** | `fase8_compattezza()` | Compatta l'orario spostando le lezioni verso le prime ore per eliminare buchi interni. |

**Slot intoccabili** (nessuna fase può modificarli):
- `origine` in `("fisso", "speciale", "fase6", "fase7", "critica")`
- `locked = True`
- `tipo_giorno` in `("STAGE", "FESTA", "SPECIALE")`

### 4d — Diagnostica Post-Motore

Stampa a console un report per la classe "3 A" e un report globale (via `diagnostica.py`). Non blocca l'esecuzione.

---

## Fase 5 — `costruisci_settimana()` → `orario_utils.py`

Converte le griglie interne (dict `{data: [slot0, slot1, ...]}}`) nel formato finale del calendario:

```python
[
  {
    "data": date(2024, 9, 2),
    "giorno_settimana": "Lunedì",
    "lezioni": [
      {"ora": time(8, 0), "materia": "Matematica", "docente": "Rossi Mario"},
      {"ora": time(9, 0), "materia": "Italiano",   "docente": "Bianchi Anna"},
      ...
    ]
  },
  ...
]
```

---

## Fase 6 — `salva_calendari()` → `orario_utils.py`

Assembla il dizionario finale da restituire al chiamante:

```python
{
    classe_id: {
        "nome_classe": "1 A",
        "ore_giornaliere": 6,
        "calendario": [ ... lista giorni ... ]
    },
    ...
}
```

---

## Fase 7 — Validazione e Cache

**File:** `validator.py`

- `set_validator_cache(calendario_per_classe, classi_info)` → salva in variabili di modulo accessibili da `/orario/diagnostica`.
- `valida_motore()` → controlla coerenza interna (slot duplicati, debiti residui, ecc.) e stampa errori a console.

Non blocca la generazione: errori vengono solo loggati.

---

## Ritorno al Route Handler (`orario.py`)

Con il dizionario `calendario` in mano, il route handler:

1. Crea un `openpyxl.Workbook()` senza il foglio default.
2. Per ogni `classe_id → dati` → crea un foglio (nome troncato a 31 caratteri).
3. Scrive intestazioni: `Data | Giorno | Ora | Materia | Docente`.
4. Per ogni giorno → per ogni lezione → scrive una riga.
5. Salva il file in `generated_calendars/calendario_YYYYMMDD_HHMMSS.xlsx`.
6. `flash("Calendario generato con successo!")` + redirect a `lista_versioni`.

---

## Struttura Dati Chiave: `cd` (classe data)

Il dizionario passato a tutte le fasi del motore ordinario:

| Chiave | Contenuto |
|--------|-----------|
| `classe` | ORM object `Classe` |
| `griglie` | `{(anno, sett): {data: [slot0..slotN]}}` |
| `giorni_per_key` | `{(anno, sett): [{"data":..., "giorno_it":...}]}` |
| `materie_attive` | `{materia_id: {nome, docente_id, debito_residuo, ore_minime_consecutive, ...}}` |
| `ore_g` | ore giornaliere massime della classe |
| `fissi_per_giorno` | `set{(data, h)}` — slot bloccati dai giorni fissi |
| `speciali_per_giorno` | `set{(data, h)}` — slot bloccati dai giorni speciali |
| `tipo_giorno` | `{data: "STAGE"|"FESTA"|"SPECIALE"|None}` |
| `libero` | slot ancora liberi (usato dal motore ordinario) |

---

## Struttura Dati Chiave: Slot

Ogni cella della griglia, una volta riempita, è un dizionario:

```python
{
    "materia_id": 3,
    "materia": "Matematica",
    "docente_id": 7,
    "docente": "Rossi Mario",    # aggiunto da costruisci_settimana
    "origine": "ordinario",      # "fisso"|"speciale"|"stage"|"critica"|"fase6"|"fase7"
    "locked": True,
    "fisso": False,
    "tipo": None,                # "STAGE"|"FESTA"|"SPECIALE" per blocchi speciali
}
```

---

## Occupazione Globale (`occupazione.py`)

Due dizionari di modulo condivisi da tutte le fasi:

| Dizionario | Chiave | Valore |
|------------|--------|--------|
| `OCCUPAZIONE_DOCENTI_GLOBALE` | `docente_id → data → {ora: True}` | Quale docente è occupato quando |
| `OCCUPAZIONE_CLASSI_GLOBALE` | `classe_id → data → {ora: True}` | Quale classe è occupata quando |

Funzioni principali:
- `occ.occupa(docente_id, classe_id, data, ora)` — segna come occupato
- `occ.libera(docente_id, data, ora)` — libera lo slot
- `occ.docente_libero(docente_id, data, ora)` — verifica disponibilità

---

## Corner Case Principali

| Punto | Problema |
|-------|----------|
| `AnnoFormativo` assente | `prepara_classi()` ritorna vuoto → calendario vuoto, nessun errore |
| Nessuna eccezione gestita | Qualsiasi errore in `genera_calendario_annuale()` → HTTP 500 grezzo |
| Sheet name collision | Due classi con nome identico fino al 31° carattere → il secondo foglio sovrascrive il primo silenziosamente |
| Cache di modulo | `CALENDARIO_CACHE` / `CLASSI_INFO_CACHE` in `validator.py` vengono azzerate al riavvio del server |
| Nessuna cache del risultato | `export_xls` e `report_vincoli` rieseguono l'intera pipeline da zero ogni volta |
| MAX_ITER = 5 | Se dopo 5 iterazioni rimane debito residuo, viene silenziosamente ignorato |
