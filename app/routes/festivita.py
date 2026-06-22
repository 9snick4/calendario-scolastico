from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, Festivita
from datetime import datetime

festivita_bp = Blueprint("festivita", __name__, url_prefix="/festivita")

@festivita_bp.route("/", methods=["GET", "POST"])
def gestione_festivita():
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
    f = Festivita.query.get_or_404(id)
    db.session.delete(f)
    db.session.commit()

    flash("Festività eliminata!", "success")
    return redirect(url_for("festivita.gestione_festivita"))
