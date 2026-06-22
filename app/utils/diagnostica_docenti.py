# app/utils/diagnostica_docenti.py

from app.models import Classe, MateriaClasse, Docente, Materia


def diagnostica_docenti_mancanti():
    """
    Controlla tutte le materie di tutte le classi e individua:
    - docente_id = None
    - docente_id = 0
    - docente inesistente
    - docente con nome vuoto
    - materie duplicate con docente incoerente
    """

    problemi = []
    docenti = {d.id: d.nome_docente for d in Docente.query.all()}
    materie = {m.id: m.nome for m in Materia.query.all()}

    for classe in Classe.query.all():
        mc_list = MateriaClasse.query.filter_by(classe_id=classe.id).all()

        for mc in mc_list:
            nome_materia = materie.get(mc.materia_id, f"Materia {mc.materia_id}")
            docente_id = mc.docente_id
            nome_classe = classe.nome_classe

            # 1) docente_id mancante
            if docente_id is None:
                problemi.append({
                    "classe": nome_classe,
                    "materia": nome_materia,
                    "problema": "docente_id = None"
                })
                continue

            # 2) docente_id = 0
            if docente_id == 0:
                problemi.append({
                    "classe": nome_classe,
                    "materia": nome_materia,
                    "problema": "docente_id = 0 (non valido)"
                })
                continue

            # 3) docente non esiste nel DB
            if docente_id not in docenti:
                problemi.append({
                    "classe": nome_classe,
                    "materia": nome_materia,
                    "problema": f"docente_id {docente_id} non esiste nel DB"
                })
                continue

            # 4) docente con nome vuoto
            if not docenti[docente_id] or docenti[docente_id].strip() == "":
                problemi.append({
                    "classe": nome_classe,
                    "materia": nome_materia,
                    "problema": f"docente_id {docente_id} ha nome vuoto"
                })
                continue

    return problemi


def stampa_diagnostica_docenti():
    problemi = diagnostica_docenti_mancanti()

    if not problemi:
        print("\n✅ Nessun problema nei docenti assegnati alle materie.\n")
        return

    print("\n❌ PROBLEMI TROVATI NEI DOCENTI DELLE MATERIE:\n")

    for p in problemi:
        print(f"- Classe {p['classe']}: {p['materia']} → {p['problema']}")

    print("\nTotale problemi:", len(problemi))
