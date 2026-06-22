from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import (
    db,
    Docente,
    VincoloDocente,
    Classe,
    GiornoSpeciale,
    Materia,
    DisponibilitaAnnua,
    GiornoFisso
)
from datetime import datetime

MAPPA_GIORNI_COMPLETI = {
    "lun": "Lunedì",
    "mar": "Martedì",
    "mer": "Mercoledì",
    "gio": "Giovedì",
    "ven": "Venerdì",
    "sab": "Sabato",
    "dom": "Domenica",
}


vincoli_bp = Blueprint("vincoli", __name__, url_prefix="/vincoli")


# INDEX
@vincoli_bp.route("/")
def index():
    return redirect(url_for("vincoli.vincoli_docenti"))


# ---------------------------------------------------------
# VINCOLI DOCENTI
# ---------------------------------------------------------
@vincoli_bp.route("/docenti", methods=["GET", "POST"])
def vincoli_docenti():
    docenti = Docente.query.order_by(Docente.nome_docente).all()
    vincoli = VincoloDocente.query.order_by(VincoloDocente.docente_id).all()

    if request.method == "POST":
        docente_id = request.form.get("docente_id")
        giorno = request.form.get("giorno")
        ora_da = request.form.get("ora_da")
        ora_a = request.form.get("ora_a")

        nuovo = VincoloDocente(
            docente_id=docente_id,
            giorno=giorno,
            ora_da=ora_da,
            ora_a=ora_a
        )
        db.session.add(nuovo)
        db.session.commit()

        flash("Vincolo docente aggiunto!", "success")
        return redirect(url_for("vincoli.vincoli_docenti"))

    return render_template("vincoli_docenti.html", docenti=docenti, vincoli=vincoli)


@vincoli_bp.route("/docenti/delete/<int:id>")
def delete_vincolo_docente(id):
    vincolo = VincoloDocente.query.get_or_404(id)
    db.session.delete(vincolo)
    db.session.commit()
    flash("Vincolo docente eliminato!", "success")
    return redirect(url_for("vincoli.vincoli_docenti"))


# ---------------------------------------------------------
# GIORNI SPECIALI
# ---------------------------------------------------------
@vincoli_bp.route("/giorni_speciali", methods=["GET", "POST"])
def giorni_speciali():
    classi = Classe.query.order_by(Classe.nome_classe).all()
    materie = Materia.query.order_by(Materia.nome).all()
    docenti = Docente.query.order_by(Docente.nome_docente).all()
    docenti_dict = {d.id: d.nome_docente for d in docenti}

    filtro_classe = request.args.get("classe_id")

    if filtro_classe:
        giorni = GiornoSpeciale.query.filter_by(classe_id=filtro_classe).order_by(GiornoSpeciale.data).all()
    else:
        giorni = GiornoSpeciale.query.order_by(GiornoSpeciale.data).all()

    if request.method == "POST":
        classe_id = request.form.get("classe_id")
        data = datetime.strptime(request.form.get("data"), "%Y-%m-%d").date()
        materia_id = request.form.get("materia_id")
        materia = Materia.query.get(materia_id).nome
        ore = int(request.form.get("ore"))
        docente_id = request.form.get("docente_id") or None

        nuovo = GiornoSpeciale(
            classe_id=classe_id,
            data=data,
            materia=materia,
            ore=ore,
            docente_id=docente_id
        )
        db.session.add(nuovo)
        db.session.commit()

        flash("Giorno speciale aggiunto!", "success")
        return redirect(url_for("vincoli.giorni_speciali"))

    return render_template(
        "giorni_speciali.html",
        classi=classi,
        giorni=giorni,
        materie=materie,
        docenti=docenti,
        filtro_classe=filtro_classe
    )



@vincoli_bp.route("/giorni_speciali/edit/<int:id>", methods=["GET", "POST"])
def edit_giorno_speciale(id):
    giorno = GiornoSpeciale.query.get_or_404(id)
    classi = Classe.query.order_by(Classe.nome_classe).all()
    materie = Materia.query.order_by(Materia.nome).all()
    docenti = Docente.query.order_by(Docente.nome_docente).all()

    if request.method == "POST":
        giorno.classe_id = request.form.get("classe_id")
        giorno.data = datetime.strptime(request.form.get("data"), "%Y-%m-%d").date()
        materia_id = request.form.get("materia_id")
        giorno.materia = Materia.query.get(materia_id).nome
        giorno.ore = int(request.form.get("ore"))
        giorno.docente_id = request.form.get("docente_id") or None

        db.session.commit()
        flash("Giorno speciale modificato!", "success")
        return redirect(url_for("vincoli.giorni_speciali"))

    return render_template(
        "edit_giorno_speciale.html",
        giorno=giorno,
        classi=classi,
        materie=materie,
        docenti=docenti
    )


@vincoli_bp.route("/giorni_speciali/delete/<int:id>")
def delete_giorno_speciale(id):
    giorno = GiornoSpeciale.query.get_or_404(id)
    db.session.delete(giorno)
    db.session.commit()
    flash("Giorno speciale eliminato!", "success")
    return redirect(url_for("vincoli.giorni_speciali"))


# ---------------------------------------------------------
# DISPONIBILITÀ ANNUA
# ---------------------------------------------------------
@vincoli_bp.route("/disponibilita_annua", methods=["GET", "POST"])
def disponibilita_annua():
    docenti = Docente.query.order_by(Docente.nome_docente).all()
    disponibilita = DisponibilitaAnnua.query.order_by(DisponibilitaAnnua.docente_id).all()

    if request.method == "POST":
        docente_id = request.form.get("docente_id")
        data_da = datetime.strptime(request.form.get("data_da"), "%Y-%m-%d").date()
        data_a = datetime.strptime(request.form.get("data_a"), "%Y-%m-%d").date()

        nuovo = DisponibilitaAnnua(
            docente_id=docente_id,
            data_da=data_da,
            data_a=data_a
        )
        db.session.add(nuovo)
        db.session.commit()

        flash("Disponibilità annua aggiunta!", "success")
        return redirect(url_for("vincoli.disponibilita_annua"))

    return render_template("disponibilita_annua.html", docenti=docenti, disponibilita=disponibilita)


@vincoli_bp.route("/disponibilita_annua/delete/<int:id>")
def delete_disponibilita_annua(id):
    disp = DisponibilitaAnnua.query.get_or_404(id)
    db.session.delete(disp)
    db.session.commit()
    flash("Disponibilità annua eliminata!", "success")
    return redirect(url_for("vincoli.disponibilita_annua"))


# ---------------------------------------------------------
# GIORNI FISSI
# ---------------------------------------------------------
@vincoli_bp.route("/giorni_fissi")
def giorni_fissi():
    classi = Classe.query.order_by(Classe.nome_classe).all()
    materie = Materia.query.order_by(Materia.nome).all()
    docenti = Docente.query.order_by(Docente.nome_docente).all()
    giorni_fissi = GiornoFisso.query.all()
    docenti_dict = {d.id: d.nome_docente for d in docenti}

    return render_template(
        "giorni_fissi.html",
        classi=classi,
        materie=materie,
        docenti=docenti,
        giorni_fissi=giorni_fissi
    )



@vincoli_bp.route("/giorni_fissi/salva", methods=["POST"])
def salva_giorno_fisso():
    classe_id = request.form.get("classe_id")
    materia_id = request.form.get("materia_id")
    docente_id = request.form.get("docente_id")
    giorno = request.form.get("giorno")
    ore = request.form.get("ore")

    if not classe_id or not materia_id or not docente_id or not giorno or not ore:
        flash("Compila tutti i campi", "danger")
        return redirect(url_for("vincoli.giorni_fissi"))

    # Normalizza il giorno (lun → Lunedì)
    giorno = giorno.strip().lower()
    giorno = MAPPA_GIORNI_COMPLETI.get(giorno, None)

    if giorno is None:
        flash("Giorno non valido", "danger")
        return redirect(url_for("vincoli.giorni_fissi"))

    nuovo = GiornoFisso(
        classe_id=int(classe_id),
        materia_id=int(materia_id),
        docente_id=int(docente_id),
        giorno=giorno,
        ore=int(ore)
    )

    db.session.add(nuovo)
    db.session.commit()

    flash("Giorno fisso salvato!", "success")
    return redirect(url_for("vincoli.giorni_fissi"))



    

    db.session.add(nuovo)
    db.session.commit()

    flash("Giorno fisso salvato!", "success")
    return redirect(url_for("vincoli.giorni_fissi"))


@vincoli_bp.route("/giorni_fissi/elimina/<int:id>", methods=["POST"])
def elimina_giorno_fisso(id):
    gf = GiornoFisso.query.get_or_404(id)
    db.session.delete(gf)
    db.session.commit()

    flash("Giorno fisso eliminato!", "success")
    return redirect(url_for("vincoli.giorni_fissi"))
