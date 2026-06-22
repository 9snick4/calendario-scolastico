# app/utils/associazioni_loader.py

from app.models import Classe

def carica_associazioni_parallele():
    """
    Usa classe_associata_id come riferimento alla classe PRINCIPALE.
    Restituisce:
        { "1C": ["1B"], "2C": ["2B"], ... }  (esempio)
    """

    associazioni = {}

    classi = Classe.query.all()
    id_to_nome = {c.id: c.nome_classe for c in classi}

    for c in classi:
        assoc_id = c.classe_associata_id

        if not assoc_id:
            continue

        if assoc_id not in id_to_nome:
            print(f"[WARN] classe_associata_id={assoc_id} non trovato per {c.nome_classe}")
            continue

        principale = id_to_nome[assoc_id]   # ← la classe referenziata è la principale
        associata  = c.nome_classe         # ← questa riga è la classe associata

        if principale == associata:
            print(f"[WARN] {principale} associata a sé stessa, ignorata.")
            continue

        associazioni.setdefault(principale, []).append(associata)

    return associazioni



def genera_doc_est_map(associazioni):
    """
    Genera automaticamente la mappa DOC EST per ogni classe associata.
    Esempio:
        {"1C": "DOC EST 1B", "4C": "DOC EST 4B"}
    """

    mappa = {}

    for principale, associate in associazioni.items():
        for c in associate:
            mappa[c] = f"DOC EST {principale}"

    return mappa
