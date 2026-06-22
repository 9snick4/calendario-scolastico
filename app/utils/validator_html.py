from markupsafe import escape

def render_html_report(conflitti_reali, conflitti_finali):
    """
    Genera un report HTML leggibile e colorato.
    """

    def blocco(titolo, conflitti, colore):
        if not conflitti:
            return f"""
            <div style="border-left: 6px solid {colore}; padding: 10px; margin: 15px 0;">
                <h3 style="margin: 0; color:{colore};">{escape(titolo)}</h3>
                <p style="margin: 5px 0;">✔ Nessun conflitto.</p>
            </div>
            """

        righe = ""
        for c in conflitti:
            righe += f"""
            <tr>
                <td>{escape(c['docente'])}</td>
                <td>{escape(str(c['data']))}</td>
                <td>{escape(str(c['ora']))}</td>
                <td>{escape(", ".join(c['classi']))}</td>
            </tr>
            """

        return f"""
        <div style="border-left: 6px solid {colore}; padding: 10px; margin: 15px 0;">
            <h3 style="margin: 0; color:{colore};">{escape(titolo)}</h3>
            <table style="width:100%; border-collapse: collapse; margin-top:10px;">
                <thead>
                    <tr style="background:#f0f0f0;">
                        <th style="padding:6px; border:1px solid #ccc;">Docente</th>
                        <th style="padding:6px; border:1px solid #ccc;">Data</th>
                        <th style="padding:6px; border:1px solid #ccc;">Ora</th>
                        <th style="padding:6px; border:1px solid #ccc;">Classi Coinvolte</th>
                    </tr>
                </thead>
                <tbody>
                    {righe}
                </tbody>
            </table>
        </div>
        """

    html = f"""
    <div style="font-family: Arial, sans-serif; padding: 20px;">
        <h2>Diagnostica Orario — Report Conflitti</h2>

        {blocco("VALIDATORE A — Conflitti REALI (griglia motore)", conflitti_reali, "#d9534f")}

        {blocco("VALIDATORE B — Conflitti nel Calendario Finale (JSON)", conflitti_finali, "#f0ad4e")}

        <div style="margin-top:20px; padding:10px; border-left:6px solid #0275d8;">
            <h3 style="margin:0; color:#0275d8;">VALIDATORE C — Confronto</h3>
            <p style="margin:5px 0;">
    """

    if not conflitti_reali and conflitti_finali:
        html += "⚠️ I conflitti sono SOLO nel calendario finale → errore di conversione, NON del motore."
    elif conflitti_reali:
        html += "❌ CI SONO CONFLITTI REALI → il motore deve essere corretto."
    else:
        html += "✔ Nessun conflitto reale o finale → orario perfetto."

    html += """
            </p>
        </div>
    </div>
    """

    return html
