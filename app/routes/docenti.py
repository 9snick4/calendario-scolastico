# app/routes/docenti.py
from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.models import Docente, db

docenti_bp = Blueprint("docenti", __name__, url_prefix="/docenti")

# LISTA DOCENTI
@docenti_bp.route("/")
def lista_docenti():
    """
    Mostra tutti i docenti ordinati alfabeticamente.
    """
    docenti = Docente.query.order_by(Docente.nome_docente).all()
    return render_template("docenti.html", docenti=docenti)

# CREA DOCENTE
@docenti_bp.route("/crea", methods=["POST"])
def crea_docente():
    """
    Crea un nuovo docente. Il nome e' obbligatorio.
    """
    nome = request.form.get("nome_docente")
    if not nome:
        flash("Il nome del docente è obbligatorio", "danger")
        return redirect(url_for("docenti.lista_docenti"))

    docente = Docente(nome_docente=nome)
    db.session.add(docente)
    db.session.commit()

    flash("Docente creato con successo!", "success")
    return redirect(url_for("docenti.lista_docenti"))

# MODIFICA DOCENTE
@docenti_bp.route("/modifica/<int:docente_id>", methods=["POST"])
def modifica_docente(docente_id):
    """
    Aggiorna il nome di un docente esistente.
    """
    docente = Docente.query.get_or_404(docente_id)
    nuovo_nome = request.form.get("nome_docente")

    if not nuovo_nome:
        flash("Il nome non può essere vuoto", "danger")
        return redirect(url_for("docenti.lista_docenti"))

    docente.nome_docente = nuovo_nome
    db.session.commit()

    flash("Docente modificato con successo!", "success")
    return redirect(url_for("docenti.lista_docenti"))

# ELIMINA DOCENTE
@docenti_bp.route("/elimina/<int:docente_id>", methods=["POST"])
def elimina_docente(docente_id):
    """
    Elimina un docente e tutti i suoi insegnamenti (cascade).
    """

    docente = Docente.query.get_or_404(docente_id)
    db.session.delete(docente)
    db.session.commit()

    flash("Docente eliminato!", "success")
    return redirect(url_for("docenti.lista_docenti"))
