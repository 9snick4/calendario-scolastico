from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, Materia

materie_bp = Blueprint("materie", __name__, url_prefix="/materie")

@materie_bp.route("/", methods=["GET", "POST"])
def lista_materie():
    materie = Materia.query.order_by(Materia.nome).all()

    # 🔥 Se clicco SALVA (aggiornamento multiplo)
    if request.method == "POST" and "salva_modifiche" in request.form:
        for m in materie:
            flag = request.form.get(f"prof_{m.id}")
            m.is_professionale = (flag == "on")
        db.session.commit()
        flash("Modifiche salvate!", "success")
        return redirect(url_for("materie.lista_materie"))

    # 🔥 Se aggiungo una nuova materia
    if request.method == "POST" and "nome" in request.form:
        nome = request.form.get("nome")
        colore = request.form.get("colore") or "#007bff"

        if Materia.query.filter_by(nome=nome).first():
            flash("Materia già presente!", "warning")
        else:
            nuova = Materia(nome=nome, colore=colore)
            db.session.add(nuova)
            db.session.commit()
            flash("Materia aggiunta!", "success")

        return redirect(url_for("materie.lista_materie"))

    return render_template("materie.html", materie=materie)


@materie_bp.route("/delete/<int:id>")
def delete_materia(id):
    materia = Materia.query.get_or_404(id)
    db.session.delete(materia)
    db.session.commit()
    flash("Materia eliminata!", "success")
    return redirect(url_for("materie.lista_materie"))
