from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, AnnoFormativo, Classe, CalendarioClasse
from datetime import datetime

anni_bp = Blueprint("anni", __name__, url_prefix="/anni")

GIORNI_COMPLETI = {
    "lun": "Lunedì",
    "mar": "Martedì",
    "mer": "Mercoledì",
    "gio": "Giovedì",
    "ven": "Venerdì",
    "sab": "Sabato",
    "dom": "Domenica",
}


@anni_bp.route("/", methods=["GET", "POST"])
def gestione_anno():
    anno = AnnoFormativo.query.first()
    classi = Classe.query.order_by(Classe.nome_classe).all()

    # ---------------------------------------------------------
    # POST: SALVATAGGIO ANNO FORMATIVO + AGGIORNAMENTO CLASSI
    # ---------------------------------------------------------
    if request.method == "POST":

        # --- Lettura date generali ---
        data_inizio_raw = request.form.get("data_inizio")
        data_fine_raw = request.form.get("data_fine")

        if not data_inizio_raw or not data_fine_raw:
            flash("Inserisci sia la data di inizio che la data di fine dell'anno formativo.", "danger")
            return redirect(url_for("anni.gestione_anno"))

        data_inizio = datetime.strptime(data_inizio_raw, "%Y-%m-%d").date()
        data_fine = datetime.strptime(data_fine_raw, "%Y-%m-%d").date()

        ora_inizio = request.form.get("ora_inizio")
        ora_fine = request.form.get("ora_fine")
        sabato = request.form.get("sabato") == "on"

        # --- Salvataggio anno formativo generale ---
        if anno:
            anno.data_inizio = data_inizio
            anno.data_fine = data_fine
            anno.ora_inizio = ora_inizio
            anno.ora_fine = ora_fine
            anno.sabato = sabato
        else:
            anno = AnnoFormativo(
                data_inizio=data_inizio,
                data_fine=data_fine,
                ora_inizio=ora_inizio,
                ora_fine=ora_fine,
                sabato=sabato
            )
            db.session.add(anno)

        # ---------------------------------------------------------
        # AGGIORNA AUTOMATICAMENTE TUTTE LE CLASSI
        # ---------------------------------------------------------
        for classe in classi:

            # Date specifiche della classe (o fallback alle generali)
            data_i_raw = request.form.get(f"classe_{classe.id}_inizio") or data_inizio_raw
            data_f_raw = request.form.get(f"classe_{classe.id}_fine") or data_fine_raw

            data_i = datetime.strptime(data_i_raw, "%Y-%m-%d").date()
            data_f = datetime.strptime(data_f_raw, "%Y-%m-%d").date()

            # Ore massime giornaliere
            ore_max = int(request.form.get(f"classe_{classe.id}_ore"))

            # Giorni selezionati (checkbox)
            giorni_selezionati = request.form.getlist(f"classe_{classe.id}_giorni")
            giorni_completi = [GIORNI_COMPLETI[g] for g in giorni_selezionati]
            classe.giorni_lezione = ",".join(giorni_completi)

            # Salva date anche nel modello Classe
            classe.data_inizio = data_i
            classe.data_fine = data_f
            classe.ore_massime_giornaliere = ore_max

            # --- Calendario classe ---
            calendario = CalendarioClasse.query.filter_by(classe_id=classe.id).first()
            if calendario:
                calendario.data_inizio = data_i
                calendario.data_fine = data_f
            else:
                db.session.add(CalendarioClasse(
                    classe_id=classe.id,
                    data_inizio=data_i,
                    data_fine=data_f
                ))

        db.session.commit()
        flash("Anno formativo e calendari classe salvati!", "success")
        return redirect(url_for("anni.gestione_anno"))

    # ---------------------------------------------------------
    # GET: PREPARA I CALENDARI PER LA PAGINA
    # ---------------------------------------------------------
    calendari = {
        classe.id: CalendarioClasse.query.filter_by(classe_id=classe.id).first()
        for classe in classi
    }

    return render_template("anni.html", anno=anno, classi=classi, calendari=calendari)


# ---------------------------------------------------------
# RESET COMPLETO ANNO FORMATIVO
# ---------------------------------------------------------
@anni_bp.route("/reset", methods=["POST"])
def reset_anno():

    AnnoFormativo.query.delete()
    CalendarioClasse.query.delete()

    for c in Classe.query.all():
        c.data_inizio = None
        c.data_fine = None
        c.giorni_lezione = None
        c.ore_massime_giornaliere = None

    db.session.commit()
    flash("Dati dell'anno formativo e delle classi resettati con successo.", "warning")
    return redirect(url_for("anni.gestione_anno"))


# ---------------------------------------------------------
# RESET SINGOLA CLASSE
# ---------------------------------------------------------
@anni_bp.route("/reset_classe/<int:classe_id>", methods=["POST"])
def reset_classe(classe_id):

    classe = Classe.query.get_or_404(classe_id)

    classe.data_inizio = None
    classe.data_fine = None
    classe.giorni_lezione = None
    classe.ore_massime_giornaliere = None

    CalendarioClasse.query.filter_by(classe_id=classe_id).delete()

    db.session.commit()
    flash(f"Dati della classe {classe.nome_classe} resettati.", "warning")
    return redirect(url_for("anni.gestione_anno"))
