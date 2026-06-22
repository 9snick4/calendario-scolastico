from app import create_app
from app.utils.diagnostica_docenti import stampa_diagnostica_docenti

app = create_app()
app.app_context().push()

stampa_diagnostica_docenti()
