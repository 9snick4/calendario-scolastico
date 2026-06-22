
from app import db


class Classe(db.Model):
    """
    Rappresenta una classe scolastica.

    Ogni classe ha un proprio intervallo di date (con fallback alle date
    globali dell'AnnoFormativo), un numero massimo di ore giornaliere e
    i giorni di lezione consentiti. Puo' essere associata a un'altra
    classe (es. classi parallele che condividono docenti) tramite il
    self-join ``classe_associata``.
    """
    id = db.Column(db.Integer, primary_key=True)
    nome_classe = db.Column(db.String(50), nullable=False, unique=True)

    # Date personalizzate per la classe
    data_inizio = db.Column(db.Date, nullable=True)
    data_fine = db.Column(db.Date, nullable=True)

    # Ore giornaliere e giorni di lezione
    ore_massime_giornaliere = db.Column(db.Integer, default=6)
    giorni_lezione = db.Column(db.String(100), default="Lunedì,Martedì,Mercoledì,Giovedì,Venrdì")

    # 🔥 NUOVO: associazione con un’altra classe
    classe_associata_id = db.Column(db.Integer, db.ForeignKey("classe.id"), nullable=True)
    classe_associata = db.relationship("Classe", remote_side=[id])

    # Relazioni
    materie_assegnate = db.relationship(
        "MateriaClasse",
        backref="classe",
        cascade="all, delete-orphan"
    )

    calendario = db.relationship(
        "CalendarioClasse",
        backref="classe",
        uselist=False,
        cascade="all, delete-orphan"
    )


class Docente(db.Model):
    """
    Rappresenta un docente.

    Il campo ``nome_docente`` e' il nome visualizzato nel calendario.
    Il valore speciale "DOC EST" indica un docente esterno/virtuale che
    viene considerato sempre disponibile dal motore di pianificazione.
    """
    id = db.Column(db.Integer, primary_key=True)
    nome_docente = db.Column(db.String(100), nullable=False)

    insegnamenti = db.relationship("MateriaClasse", backref="docente_rel", cascade="all, delete-orphan")


class MateriaClasse(db.Model):
    """
    Tabella di giunzione tra Classe e Materia.

    Oltre alla relazione, porta:
    - ``ore_annuali``: quante ore devono essere pianificate nell'anno;
    - ``docente_id``: il docente assegnato a quella materia per quella classe;
    - ``ore_minime_consecutive``: numero minimo di ore che il motore deve
      piazzare in blocco (es. 2 = mai ore singole isolate).
    """
    id = db.Column(db.Integer, primary_key=True)

    classe_id = db.Column(db.Integer, db.ForeignKey("classe.id"), nullable=False)

    materia_id = db.Column(db.Integer, db.ForeignKey("materia.id"), nullable=False)
    materia = db.relationship("Materia")

    ore_annuali = db.Column(db.Integer, nullable=False)

    docente_id = db.Column(db.Integer, db.ForeignKey("docente.id"), nullable=False)
    docente = db.relationship("Docente")

    ore_minime_consecutive = db.Column(db.Integer, nullable=False, default=1)


class AnnoFormativo(db.Model):
    """
    Configurazione globale dell'anno scolastico.

    Contiene le date di inizio/fine, l'orario di entrata/uscita e se il
    sabato e' un giorno lavorativo. Questi valori sono usati come fallback
    per le classi prive di date personalizzate.
    """
    id = db.Column(db.Integer, primary_key=True)
    data_inizio = db.Column(db.Date, nullable=False)
    data_fine = db.Column(db.Date, nullable=False)

    ora_inizio = db.Column(db.String(5), default="08:00")
    ora_fine = db.Column(db.String(5), default="14:00")
    sabato = db.Column(db.Boolean, default=False)


class CalendarioClasse(db.Model):
    """
    Memorizza le date effettive di calendario per una singola classe.

    Viene creato/aggiornato automaticamente quando si salvano le
    impostazioni dell'anno formativo.
    """
    id = db.Column(db.Integer, primary_key=True)
    classe_id = db.Column(db.Integer, db.ForeignKey("classe.id"), nullable=False)
    data_inizio = db.Column(db.Date, nullable=False)
    data_fine = db.Column(db.Date, nullable=False)





class Vincolo(db.Model):
    """
    Modello generico di vincolo (attualmente placeholder).

    La logica reale di vincolo e' gestita da VincoloDocente e GiornoFisso.
    """
    id = db.Column(db.Integer, primary_key=True)
    descrizione = db.Column(db.String(255), nullable=False)


class VincoloDocente(db.Model):
    """
    Fascia oraria di disponibilita' di un docente in un dato giorno.

    Es.: Rossi disponibile Lunedi' 08:00-12:00. Il motore non assegna
    ore fuori da questa fascia.

    CORNER CASE: se esistono vincoli per un docente ma NESSUNO copre il
    giorno richiesto, il docente viene considerato NON disponibile quel
    giorno (logica whitelisting: la disponibilita' deve essere dichiarata
    esplicitamente).
    """
    id = db.Column(db.Integer, primary_key=True)
    docente_id = db.Column(db.Integer, db.ForeignKey("docente.id"), nullable=False)
    giorno = db.Column(db.String(20), nullable=False)
    ora_da = db.Column(db.String(5), nullable=False)
    ora_a = db.Column(db.String(5), nullable=False)

    docente = db.relationship("Docente", backref="disponibilita")


class OrarioGenerato(db.Model):
    """
    Snapshot di un singolo slot orario generato dal motore.

    NOTA: al momento NON viene popolato dal flusso principale;
    il calendario viene restituito come struttura in memoria da
    genera_calendario_annuale() senza passare per questa tabella.
    """
    id = db.Column(db.Integer, primary_key=True)
    classe_id = db.Column(db.Integer, db.ForeignKey("classe.id"), nullable=False)
    giorno = db.Column(db.String(10), nullable=False)
    ora = db.Column(db.Integer, nullable=False)
    materia = db.Column(db.String(100), nullable=False)
    docente = db.Column(db.String(100), nullable=False)


class Festivita(db.Model):
    """
    Periodo di festivita' (es. Natale, Pasqua, ponti).

    Tutti i giorni compresi tra data_inizio e data_fine vengono marcati
    FESTA: nessuna lezione ordinaria puo' essere piazzata in quei giorni.
    """
    id = db.Column(db.Integer, primary_key=True)
    data_inizio = db.Column(db.Date, nullable=False)
    data_fine = db.Column(db.Date, nullable=False)
    descrizione = db.Column(db.String(255), nullable=True)


class GiornoSpeciale(db.Model):
    """
    Attivita' speciale per una classe in una data precisa.

    Il motore piazza prima le ore indicate, poi blocca tutti gli slot
    rimasti come SPECIALE_VUOTO, impedendo al piazzamento ordinario di
    usarli. Solo il docente specificato (o nessuno) e' valido quel giorno.
    """
    id = db.Column(db.Integer, primary_key=True)
    classe_id = db.Column(db.Integer, db.ForeignKey("classe.id"), nullable=False)
    data = db.Column(db.Date, nullable=False)
    materia = db.Column(db.String(100), nullable=False)
    ore = db.Column(db.Integer, nullable=False)

    docente_id = db.Column(db.Integer, db.ForeignKey("docente.id"), nullable=True)
    docente = db.relationship("Docente")

    classe = db.relationship("Classe", backref="giorni_speciali")


class Materia(db.Model):
    """
    Materia di insegnamento.

    Il flag ``is_professionale`` separa materie professionalizzanti da
    quelle comuni; puo' essere usato per logiche di piazzamento differenti.
    """
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    colore = db.Column(db.String(20), default="#007bff")
    is_professionale = db.Column(db.Boolean, default=False)


class DisponibilitaAnnua(db.Model):
    """
    Periodo di disponibilita' annuale di un docente (assenze lunghe,
    distacchi, ecc.).

    NOTA: attualmente registrata ma NON controllata attivamente dal
    motore di piazzamento. Da integrare per supportare assenze estese.
    """
    id = db.Column(db.Integer, primary_key=True)
    docente_id = db.Column(db.Integer, db.ForeignKey("docente.id"), nullable=False)

    data_da = db.Column(db.Date, nullable=False)
    data_a = db.Column(db.Date, nullable=False)

    docente = db.relationship("Docente", backref="disponibilita_annua")


class GiornoFisso(db.Model):
    """
    Vincolo fisso: una materia deve avere N ore in uno specifico giorno
    della settimana, ogni settimana.

    Es.: Matematica ha sempre 2 ore il Martedi'. Questi blocchi vengono
    piazzati per primi (fase FISSI) e marcati come locked.
    """
    id = db.Column(db.Integer, primary_key=True)

    classe_id = db.Column(db.Integer, db.ForeignKey("classe.id"), nullable=False)
    materia_id = db.Column(db.Integer, db.ForeignKey("materia.id"), nullable=False)
    docente_id = db.Column(db.Integer, db.ForeignKey("docente.id"), nullable=False)

    giorno = db.Column(db.String(10), nullable=False)
    ore = db.Column(db.Integer, nullable=False, default=1)

    classe = db.relationship("Classe")
    materia = db.relationship("Materia")
    docente = db.relationship("Docente")


class Stage(db.Model):
    """
    Periodi di stage per una classe (fino a 2 periodi distinti).

    Durante i giorni di stage (filtrati dal campo ``giorni_stage``) la
    giornata viene riempita con il blocco STAGE; il motore ordinario non
    puo' piazzare nulla in quei giorni.
    """
    id = db.Column(db.Integer, primary_key=True)
    classe_id = db.Column(db.Integer, db.ForeignKey("classe.id"), nullable=False)

    periodo_stage_1_da = db.Column(db.Date)
    periodo_stage_1_a = db.Column(db.Date)
    periodo_stage_2_da = db.Column(db.Date)
    periodo_stage_2_a = db.Column(db.Date)

    # 🔥 nuovo campo
    giorni_stage = db.Column(db.String(50), default="Lunedì,Martedì,Mercoledì,Giovedì,Venerdì")

    classe = db.relationship("Classe")
