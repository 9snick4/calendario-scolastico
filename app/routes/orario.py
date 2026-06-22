# app/routes/orario.py

import os
from datetime import datetime
from io import BytesIO

import openpyxl
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)

from app.models import (
    Docente,
    GiornoFisso,
    Stage,
    db,
)
from app.utils import orario_utils
from app.utils.calendario_generator import genera_calendario_annuale

orario_bp = Blueprint("orario", __name__, url_prefix="/orario")

REPORT_VINCOLI = {}

# ============================================================
# 1) GENERA CALENDARIO (POST)
# ============================================================

@orario_bp.route("/genera", methods=["POST"])
def genera_calendario():
    """
    POST /orario/genera
    Avvia la generazione del calendario e salva il risultato su disco.

    Flusso:
    1. Chiama genera_calendario_annuale() che esegue l'intera pipeline
       (stage -> festivita -> giorni speciali -> giorni fissi -> motore
       ordinario a 8 fasi).
    2. Crea un file Excel con un foglio per ogni classe.
    3. Salva il file nella cartella generated_calendars/ con timestamp.
    4. Reindirizza alla lista versioni.

    CORNER CASE: se genera_calendario_annuale() lancia un'eccezione
    (es. AnnoFormativo assente, classi senza date) Flask la propagera'
    come HTTP 500. Non c'e' gestione esplicita degli errori qui.

    CORNER CASE: la cartella generated_calendars/ viene creata se non
    esiste (makedirs con exist_ok=True).

    CORNER CASE: il nome del foglio Excel viene troncato a 31 caratteri
    (limite di openpyxl). Se due classi hanno nomi che differiscono solo
    oltre il 31esimo carattere, i fogli potrebbero collidere e il secondo
    sovrascrivere il primo silenziosamente.
    """
    calendario = genera_calendario_annuale()

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    for _, dati in calendario.items():
        ws = wb.create_sheet(title=dati["nome_classe"][:31])

        ws.cell(row=1, column=1, value="Data")
        ws.cell(row=1, column=2, value="Giorno")
        ws.cell(row=1, column=3, value="Ora")
        ws.cell(row=1, column=4, value="Materia")
        ws.cell(row=1, column=5, value="Docente")

        row = 2
        for giorno in dati["calendario"]:
            data_str = giorno["data"].strftime("%d/%m/%Y")
            giorno_label = giorno["giorno_settimana"]

            for lezione in giorno["lezioni"]:
                ora_str = lezione["ora"].strftime("%H:%M")
                ws.cell(row=row, column=1, value=data_str)
                ws.cell(row=row, column=2, value=giorno_label)
                ws.cell(row=row, column=3, value=ora_str)
                ws.cell(row=row, column=4, value=lezione["materia"])
                ws.cell(row=row, column=5, value=lezione["docente"])
                row += 1

    save_folder = os.path.join(current_app.root_path, "generated_calendars")
    os.makedirs(save_folder, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"calendario_{timestamp}.xlsx"
    filepath = os.path.join(save_folder, filename)

    wb.save(filepath)

    flash("Calendario generato con successo!", "success")
    return redirect(url_for("orario.lista_versioni"))

# ============================================================
# 2) LISTA VERSIONI (GET)
# ============================================================

@orario_bp.route("/")
@orario_bp.route("/versioni")
def lista_versioni():
    """
    GET /orario/  e  GET /orario/versioni
    Elenca tutti i file Excel generati in precedenza, ordinati per data
    discendente (il piu' recente in cima).

    CORNER CASE: se la cartella generated_calendars/ non esiste viene
    creata vuota (makedirs con exist_ok=True) e la lista sara' vuota.

    CORNER CASE: l'elenco proviene da os.listdir(), che restituisce i
    file in ordine arbitrario del filesystem; sorted(..., reverse=True)
    garantisce l'ordinamento solo se i nomi contengono il timestamp nel
    formato YYYYMMDD_HHMMSS (come generato da genera_calendario).
    Se un file ha un nome diverso, potrebbe essere posizionato fuori
    dall'ordine cronologico atteso.
    """
    save_folder = os.path.join(current_app.root_path, "generated_calendars")
    os.makedirs(save_folder, exist_ok=True)

    files = sorted(os.listdir(save_folder), reverse=True)

    return render_template("genera_calendario.html", files=files)

# ============================================================
# 3) DOWNLOAD VERSIONE
# ============================================================

@orario_bp.route("/download/<filename>")
def download_calendario(filename):
    """
    GET /orario/download/<filename>
    Invia al browser il file Excel richiesto come attachment.

    CORNER CASE DI SICUREZZA: send_from_directory() di Flask impedisce
    il path traversal (es. filename='../../etc/passwd') restituendo 404
    se il file non si trova dentro la cartella specificata.
    Tuttavia il nome file arriva direttamente dall'URL senza validazione
    esplicita: assicurarsi che solo utenti autorizzati possano accedere
    a questa rotta.
    """
    folder = os.path.join(current_app.root_path, "generated_calendars")
    return send_from_directory(folder, filename, as_attachment=True)

# ============================================================
# 4) EXPORT XLS (versione singola)
# ============================================================

@orario_bp.route("/export_xls")
def export_xls():
    """
    GET /orario/export_xls
    Genera il calendario ON-THE-FLY e lo invia direttamente al browser
    senza salvarlo su disco.

    Differenza da genera_calendario: questo percorso NON salva il file e
    non appare nella lista versioni. Utile per un download immediato.

    CORNER CASE: genera_calendario_annuale() viene chiamata due volte se
    l'utente usa sia /genera che /export_xls nella stessa sessione,
    rieseguendo l'intera pipeline due volte. Questo puo' essere costoso
    con molte classi.

    CORNER CASE: il foglio 'Indice' viene creato ma non popolato (rimane
    vuoto). Potrebbe creare confusione nell'utente.

    CORNER CASE: stesso problema di troncamento nomi foglio a 31 caratteri
    presente in genera_calendario.
    """
    calendario = genera_calendario_annuale()

    wb = openpyxl.Workbook()
    wb.active.title = "Indice"

    for _, dati in calendario.items():
        ws = wb.create_sheet(title=dati["nome_classe"][:31])

        ws.cell(row=1, column=1, value="Data")
        ws.cell(row=1, column=2, value="Giorno")
        ws.cell(row=1, column=3, value="Ora")
        ws.cell(row=1, column=4, value="Materia")
        ws.cell(row=1, column=5, value="Docente")

        row = 2
        for giorno in dati["calendario"]:
            data_str = giorno["data"].strftime("%d/%m/%Y")
            giorno_label = giorno["giorno_settimana"]

            for lezione in giorno["lezioni"]:
                ora_str = lezione["ora"].strftime("%H:%M")
                ws.cell(row=row, column=1, value=data_str)
                ws.cell(row=row, column=2, value=giorno_label)
                ws.cell(row=row, column=3, value=ora_str)
                ws.cell(row=row, column=4, value=lezione["materia"])
                ws.cell(row=row, column=5, value=lezione["docente"])
                row += 1

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="calendario_scolastico.xlsx",
    )

# ============================================================
# 5) REPORT VINCOLI
# ============================================================

@orario_bp.route("/report_vincoli")
def report_vincoli():
    """
    GET /orario/report_vincoli
    Genera il calendario e analizza le violazioni dei vincoli.

    Controlla per ogni giorno di ogni classe:
    a) STAGE: lezioni diverse da STAGE piazzate durante un periodo di stage.
    b) GIORNI SPECIALI: lezioni piazzate oltre le ore del giorno speciale.
    c) GIORNI FISSI: la materia fissa non ha il numero minimo di ore richieste.
    d) DOCENTI: il docente non e' disponibile nell'ora in cui e' stato assegnato.

    CORNER CASE: rigenera il calendario da zero con una nuova chiamata a
    genera_calendario_annuale(). Questo significa che il report non analizza
    un calendario gia' salvato, ma uno appena calcolato. Se i dati sono
    cambiati tra la generazione e il controllo, i risultati potrebbero
    differire dal file .xlsx salvato.

    CORNER CASE: il controllo dei giorni speciali (b) usa gs.ore come
    soglia, ma gs e' il primo GiornoSpeciale trovato per quella data
    tramite orario_utils.giorno_speciale_classe(). Se ci sono piu' giorni
    speciali nella stessa data per la stessa classe, solo il primo viene
    usato per il controllo della soglia; gli altri non vengono considerati.

    CORNER CASE: il controllo dei giorni fissi (c) confronta il numero di
    occorrenze della materia in un singolo giorno con gf.ore. Questo e'
    corretto solo se il GiornoFisso si applica a quel singolo giorno. Con
    piu' record GiornoFisso per la stessa materia in giorni diversi, il
    report puo' segnalare falsi positivi.

    CORNER CASE: il controllo del docente (d) usa l'indice di posizione
    della lezione come indice_ora. Questo e' corretto solo se le lezioni
    sono gia' nell'ordine dell'orario (indice 0 = prima ora, ecc.).

    CORNER CASE: se il docente non viene trovato nel DB tramite
    Docente.query.filter_by(nome_docente=...).first(), il check viene
    saltato silenziosamente (continue). Docenti con nomi leggermente
    diversi (spazi, maiuscole) non vengono controllati.
    """
    calendario = genera_calendario_annuale()
    violazioni = []

    for classe_id, dati in calendario.items():
        nome_classe = dati["nome_classe"]
        calendario_classe = dati["calendario"]

        giorni_fissi = GiornoFisso.query.filter_by(classe_id=classe_id).all()

        for giorno in calendario_classe:
            data = giorno["data"]
            giorno_it = giorno["giorno_settimana"]
            lezioni = giorno["lezioni"]

            # Vincoli usando orario_utils
            if orario_utils.classe_in_stage_giorno(classe_id, data):
                for l in lezioni:
                    if l["materia"] not in ("", "STAGE"):
                        violazioni.append(
                            f"{nome_classe} — {data}: lezione '{l['materia']}' durante STAGE"
                        )

            gs = orario_utils.giorno_speciale_classe(classe_id, data)
            if gs:
                for l in lezioni[gs.ore:]:
                    if l["materia"] not in ("", "BLOCCO_SPECIALE"):
                        violazioni.append(
                            f"{nome_classe} — {data}: lezioni oltre il giorno speciale"
                        )

            for gf in giorni_fissi:
                if gf.giorno == giorno_it:
                    count = sum(1 for l in lezioni if l["materia"] == gf.materia.nome)
                    if count < gf.ore:
                        violazioni.append(
                            f"{nome_classe} — {data}: giorno fisso '{gf.materia.nome}' non rispettato"
                        )

            for idx, l in enumerate(lezioni):
                if not l["docente"]:
                    continue

                docente_nome = l["docente"]
                docente = Docente.query.filter_by(nome_docente=docente_nome).first()
                if not docente:
                    continue

                if not orario_utils.docente_disponibile(docente.id, giorno_it, idx):
                    violazioni.append(
                        f"{nome_classe} — {data}: docente {docente_nome} non disponibile alle {l['ora']}"
                    )

    if not violazioni:
        return render_template("report_vincoli.html", report=["TUTTO OK — nessun vincolo violato"])

    return render_template("report_vincoli.html", report=violazioni)

# ============================================================
# 6) DELETE STAGE
# ============================================================

@orario_bp.route("/stage/delete/<int:classe_id>", methods=["POST"])
def delete_stage(classe_id):
    """
    POST /orario/stage/delete/<classe_id>
    Elimina il record di stage per la classe specificata.

    CORNER CASE: se non esiste un record Stage per quella classe, la
    funzione non fa nulla (no errore) e reindirizza silenziosamente.

    CORNER CASE: reindirizza a request.referrer (la pagina precedente).
    Se il referrer e' None (es. richiesta diretta senza header Referer),
    usa url_for('orario.lista_versioni') come fallback.
    """
    stage = Stage.query.filter_by(classe_id=classe_id).first()
    if stage:
        db.session.delete(stage)
        db.session.commit()

    return redirect(request.referrer or url_for("orario.lista_versioni"))

# ============================================================
# 7) DIAGNOSTICA (VALIDATORE A+B+C)
# ============================================================

@orario_bp.route("/diagnostica")
def diagnostica():
    """
    GET /orario/diagnostica
    Mostra il report diagnostico del ULTIMO calendario generato in memoria.

    Dipende da CALENDARIO_CACHE e CLASSI_INFO_CACHE in app.utils.validator,
    popolati da set_validator_cache() al termine di genera_calendario_annuale().

    CORNER CASE: se il calendario non e' ancora stato generato in questa
    sessione (CALENDARIO_CACHE e CLASSI_INFO_CACHE sono None), la rotta
    restituisce una pagina con il messaggio 'Nessun calendario generato.'
    senza errori.

    CORNER CASE: le cache sono variabili di modulo in validator.py;
    vengono azzerate ad ogni riavvio del server. Se il server viene
    riavviato dopo una generazione, questa rotta mostra il messaggio
    'Nessun calendario generato.' anche se esistono file .xlsx su disco.

    CORNER CASE: il controllo usa 'if calendario is None or classi_info
    is None' invece di 'if not calendario'. Questo e' intenzionale:
    un dizionario vuoto ({}) e' considerato diverso da None e verrebbe
    passato a stampa_report(), che potrebbe comportarsi in modo
    inatteso con un calendario vuoto.
    """
    from app.utils.validator import CALENDARIO_CACHE, CLASSI_INFO_CACHE, stampa_report

    calendario = CALENDARIO_CACHE
    classi_info = CLASSI_INFO_CACHE

    # ⚠️ Controllo corretto: verifica solo None, non dict vuoti
    if calendario is None or classi_info is None:
        return "<h3>Nessun calendario generato.</h3>"

    html = stampa_report(calendario, classi_info)
    return html
