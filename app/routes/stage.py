# app/routes/stage.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, Classe, Stage
from datetime import datetime

stage_bp = Blueprint("stage", __name__, url_prefix="/stage")

# LISTA + FORM
@stage_bp.route("/")
def gestione_stage():
    classi = Classe.query.order_by(Classe.nome_classe).all()
    stage_dati = Stage.query.all()
    return render_template("stage.html", classi=classi, stage_dati=stage_dati)

# CREA O MODIFICA STAGE
@stage_bp.route("/salva", methods=["POST"])
def salva_stage():
    classe_id = request.form.get("classe_id")

    if not classe_id:
        flash("Seleziona una classe", "danger")
        return redirect(url_for("stage.gestione_stage"))

    # Recupera o crea record
    stage = Stage.query.filter_by(classe_id=classe_id).first()
    if not stage:
        stage = Stage(classe_id=classe_id)
        db.session.add(stage)

    # Funzione per convertire le date
    def parse_date(value):
        return datetime.strptime(value, "%Y-%m-%d").date() if value else None

    # Salva date stage
    stage.periodo_stage_1_da = parse_date(request.form.get("stage1_da"))
    stage.periodo_stage_1_a = parse_date(request.form.get("stage1_a"))
    stage.periodo_stage_2_da = parse_date(request.form.get("stage2_da"))
    stage.periodo_stage_2_a = parse_date(request.form.get("stage2_a"))

    # 🔥 Salva giorni stage (checkbox)
    giorni_stage = request.form.getlist("giorni_stage")

    # Se per qualche motivo non arriva nulla, metti default Lun–Ven
    if not giorni_stage:
        giorni_stage = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]

    stage.giorni_stage = ",".join(giorni_stage)

    db.session.commit()

    flash("Dati di stage salvati con successo!", "success")
    return redirect(url_for("stage.gestione_stage"))
