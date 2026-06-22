from app import create_app, db

app = create_app()

with app.app_context():
    # Importa SOLO i modelli che esistono davvero

    print("🔧 Creazione del database...")
    db.drop_all()
    db.create_all()
    print("✅ Database creato correttamente!")
