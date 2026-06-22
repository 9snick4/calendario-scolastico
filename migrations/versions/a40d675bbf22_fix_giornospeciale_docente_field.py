"""Fix GiornoSpeciale docente field

Revision ID: a40d675bbf22
Revises: 34252539bada
Create Date: 2026-01-13 21:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = 'a40d675bbf22'
down_revision = '34252539bada'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('giorno_speciale', schema=None) as batch_op:
        # Aggiungiamo docente_id SOLO se non esiste già
        batch_op.add_column(sa.Column('docente_id', sa.Integer(), nullable=True))
        # NON tocchiamo la colonna 'docente' perché non esiste più


def downgrade():
    with op.batch_alter_table('giorno_speciale', schema=None) as batch_op:
        batch_op.drop_column('docente_id')
