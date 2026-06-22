from app import create_app

app = create_app()

if __name__ == "__main__":
    # 🔥 IMPORTANTISSIMO:
    # - debug=False evita il doppio processo
    # - use_reloader=False evita il doppio import dei moduli
    import sys

    print("\n=== MODULI OCCUPAZIONE CARICATI ===")
    for name, module in sys.modules.items():
        if "occupazione" in name.lower():
            print(name, "→", module)
    print("===================================\n")

    
    app.run(debug=False, use_reloader=False)
