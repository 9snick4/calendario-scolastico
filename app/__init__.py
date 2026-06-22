import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()

def create_app():
    # Attiva la cartella instance/
    app = Flask(__name__, instance_relative_config=True)

    # Assicura che la cartella instance esista
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    # Percorso del database dentro instance/
    db_path = os.path.join(app.instance_path, "orario_scolastico.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = "supersegreto"

    # Debug: mostra il percorso reale del DB
    print("📌 DATABASE PATH:", app.config["SQLALCHEMY_DATABASE_URI"])

    # Inizializza estensioni
    db.init_app(app)
    migrate.init_app(app, db)

    # Importa le route
    from app.routes.home import home_bp
    from app.routes.classi import classi_bp
    from app.routes.docenti import docenti_bp
    from app.routes.anni import anni_bp
    from app.routes.stage import stage_bp
    from app.routes.vincoli import vincoli_bp
    from app.routes.festivita import festivita_bp
    from app.routes.materie import materie_bp
    
    from app.routes.orario import orario_bp

    # Registra blueprint
    app.register_blueprint(home_bp)
    app.register_blueprint(classi_bp)
    app.register_blueprint(materie_bp)
    app.register_blueprint(docenti_bp)
    app.register_blueprint(anni_bp)
    app.register_blueprint(stage_bp)
    app.register_blueprint(vincoli_bp)
    app.register_blueprint(festivita_bp)
    app.register_blueprint(orario_bp)
    
    
    # app.register_blueprint(motore_bp)

    return app
