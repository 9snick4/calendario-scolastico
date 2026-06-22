# app/routes/classi.py

from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import db, Classe, Docente, Materia, MateriaClasse

classi_bp = Blueprint("classi", __name__, url_prefix="/classi")


# ---------------------------------------------------------
# LISTA CLASSI + CREA CLASSE + SALVA ASSOCIAZIONI
# ---------------------------------------------------------
@classi_bp.route("/", methods=["GET", "POST"])
def lista_classi():

    # 🔥 SALVATAGGIO ASSOCIAZIONI
    if request.method == "POST" and "salva_associazioni" in request.form:
        classi = Classe.query.all()
        for c in classi:
            assoc = request.form.get(f"assoc_{c.id}")
            if assoc == "none":
                c.classe_associata_id = None
            else:
                c.classe_associata_id = int(assoc)
        db.session.commit()
        flash("Associazioni aggiornate!", "success")
        return redirect(url_for("classi.lista_classi"))

    # 🔥 CREAZIONE NUOVA CLASSE
    if request.method == "POST" and "nome_classe" in request.form:
        nome = request.form.get("nome_classe")
        if not nome:
            flash("Il nome della classe è obbligatorio", "danger")
            return redirect(url_for("classi.lista_classi"))

        nuova = Classe(nome_classe=nome)
        db.session.add(nuova)
        db.session.commit()

        flash("Classe creata!", "success")
        return redirect(url_for("classi.lista_classi"))

    classi = Classe.query.order_by(Classe.nome_classe).all()
    return render_template("classi.html", classi=classi)


# ---------------------------------------------------------
# ELIMINA CLASSE
# ---------------------------------------------------------
@classi_bp.route("/elimina/<int:classe_id>", methods=["POST"])
def elimina_classe(classe_id):
    classe = Classe.query.get_or_404(classe_id)
    db.session.delete(classe)
    db.session.commit()

    flash("Classe eliminata!", "success")
    return redirect(url_for("classi.lista_classi"))


# ---------------------------------------------------------
# PAGINA MATERIE DELLA CLASSE
# ---------------------------------------------------------
@classi_bp.route("/<int:classe_id>/materie")
def materie_classe(classe_id):
    classe = Classe.query.get_or_404(classe_id)

    materie = Materia.query.order_by(db.func.lower(Materia.nome)).all()
    docenti = Docente.query.order_by(Docente.nome_docente).all()
    materie_classe = (
        MateriaClasse.query
        .filter_by(classe_id=classe_id)
        .join(Materia)
        .order_by(db.func.lower(Materia.nome))
        .all()
    )
    
    
    
    
    MateriaClasse.query.filter_by(classe_id=classe_id).all()

    # 🔥 Calcolo totale ore annuali già inserite
    totale_ore = sum(mc.ore_annuali for mc in materie_classe)

    return render_template(
        "classi_materie.html",
        classe=classe,
        materie=materie,
        docenti=docenti,
        materie_classe=materie_classe,
        totale_ore=totale_ore
    )



# ---------------------------------------------------------
# CREA MATERIA PER LA CLASSE (ORE ANNUALI)
# ---------------------------------------------------------
@classi_bp.route("/<int:classe_id>/materie/crea", methods=["POST"])
def crea_materia_classe(classe_id):
    materia_id = request.form.get("materia_id")
    ore_annuali = request.form.get("ore_annuali")
    docente_id = request.form.get("docente_id")
    ore_minime = request.form.get("ore_minime_consecutive")

    if not materia_id or not ore_annuali or not docente_id or not ore_minime:
        flash("Compila tutti i campi", "danger")
        return redirect(url_for("classi.materie_classe", classe_id=classe_id))

    nuova = MateriaClasse(
        classe_id=classe_id,
        materia_id=int(materia_id),
        ore_annuali=int(ore_annuali),
        docente_id=int(docente_id),
        ore_minime_consecutive=int(ore_minime)
    )

    db.session.add(nuova)
    db.session.commit()

    flash("Materia aggiunta alla classe!", "success")
    return redirect(url_for("classi.materie_classe", classe_id=classe_id))


# ---------------------------------------------------------
# ELIMINA MATERIA DALLA CLASSE
# ---------------------------------------------------------
@classi_bp.route("/materie/elimina/<int:materia_classe_id>", methods=["POST"])
def elimina_materia_classe(materia_classe_id):
    mc = MateriaClasse.query.get_or_404(materia_classe_id)
    classe_id = mc.classe_id

    db.session.delete(mc)
    db.session.commit()

    flash("Materia rimossa dalla classe!", "success")
    return redirect(url_for("classi.materie_classe", classe_id=classe_id))


# ---------------------------------------------------------
# SALVA MODIFICHE MATERIE DELLA CLASSE
# ---------------------------------------------------------
@classi_bp.route("/<int:classe_id>/materie/salva", methods=["POST"])
def salva_modifiche_materie(classe_id):
    classe = Classe.query.get_or_404(classe_id)

    # 🔥 1. Salvo le modifiche già presenti nella tabella
    materie_classe = MateriaClasse.query.filter_by(classe_id=classe_id).all()

    for mc in materie_classe:
        ore = request.form.get(f"ore_{mc.id}")
        minime = request.form.get(f"minime_{mc.id}")
        docente = request.form.get(f"docente_{mc.id}")

        if ore:
            mc.ore_annuali = int(ore)
        if minime:
            mc.ore_minime_consecutive = int(minime)
        if docente:
            mc.docente_id = int(docente)

    # 🔥 2. Se la classe ha un’associata, eredito le materie NON professionali
    if classe.classe_associata_id:
        classe_assoc = Classe.query.get(classe.classe_associata_id)

        # Recupero il docente "DOC EST"
        doc_est = Docente.query.filter_by(nome_docente="DOC EST").first()
        if not doc_est:
            doc_est = Docente(nome_docente="DOC EST")
            db.session.add(doc_est)
            db.session.commit()

        # Recupero le materie NON professionali della classe associata
        materie_assoc = (
            MateriaClasse.query
            .join(Materia)
            .filter(
                MateriaClasse.classe_id == classe_assoc.id,
                Materia.is_professionale == False
            )
            .all()
        )

        # 🔥 3. Copio nella classe corrente solo quelle che non esistono già
        for mc_assoc in materie_assoc:
            esiste = MateriaClasse.query.filter_by(
                classe_id=classe_id,
                materia_id=mc_assoc.materia_id
            ).first()

            if not esiste:
                nuovo = MateriaClasse(
                    classe_id=classe_id,
                    materia_id=mc_assoc.materia_id,
                    docente_id=doc_est.id,
                    ore_annuali=mc_assoc.ore_annuali,
                    ore_minime_consecutive=mc_assoc.ore_minime_consecutive
                )
                db.session.add(nuovo)

    db.session.commit()
    flash("Modifiche salvate!", "success")
    return redirect(url_for("classi.materie_classe", classe_id=classe_id))
