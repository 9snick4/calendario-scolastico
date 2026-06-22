from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.models import Festivita, db

festivita_bp = Blueprint("festivita", __name__, url_prefix="/festivita")

@festivita_bp.route("/", methods=["GET", "POST"])
def gestione_festivita():
    """
    GET  /festivita/ — mostra tutti i periodi di festivita'.
    POST /festivita/ — aggiunge un nuovo periodo (data_inizio, data_fine,
                       descrizione opzionale).

    Entrambe le date sono obbligatorie; se mancano si mostra un errore.
    """
    festivita = Festivita.query.order_by(Festivita.data_inizio).all()

    if request.method == "POST":
        data_inizio = request.form.get("data_inizio")
        data_fine = request.form.get("data_fine")
        descrizione = request.form.get("descrizione")

        if not data_inizio or not data_fine:
            flash("Inserisci entrambe le date", "danger")
            return redirect(url_for("festivita.gestione_festivita"))

        data_inizio = datetime.strptime(data_inizio, "%Y-%m-%d").date()
        data_fine = datetime.strptime(data_fine, "%Y-%m-%d").date()

        nuova = Festivita(
            data_inizio=data_inizio,
            data_fine=data_fine,
            descrizione=descrizione
        )

        db.session.add(nuova)
        db.session.commit()

        flash("Periodo di festività aggiunto!", "success")
        return redirect(url_for("festivita.gestione_festivita"))

    return render_template("festivita.html", festivita=festivita)


@festivita_bp.route("/elimina/<int:id>", methods=["POST"])
def elimina_festivita(id):
    """
    Elimina un periodo di festivita'. Gli eventuali calendari gia' generati
    in memoria NON vengono rigenerati automaticamente: bisogna rieseguire
    la generazione per riflettere la modifica.
    """
    f = Festivita.query.get_or_404(id)
    db.session.delete(f)
    db.session.commit()

    flash("Festività eliminata!", "success")
    return redirect(url_for("festivita.gestione_festivita"))
