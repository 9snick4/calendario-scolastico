"""Add docente_id to GiornoSpeciale

Revision ID: 34252539bada
Revises: 98719fe3bafc
Create Date: 2026-01-13 20:52:16.530921

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '34252539bada'
down_revision = '98719fe3bafc'
branch_labels = None
depends_on = None


def upgrade():
    # Aggiorniamo SOLO giorno_speciale
    with op.batch_alter_table('giorno_speciale', schema=None) as batch_op:
        batch_op.add_column(sa.Column('docente_id', sa.Integer(), nullable=True))
        batch_op.drop_column('docente')


def downgrade():
    # Ripristino SOLO giorno_speciale
    with op.batch_alter_table('giorno_speciale', schema=None) as batch_op:
        batch_op.add_column(sa.Column('docente', sa.VARCHAR(length=100), nullable=True))
        batch_op.drop_column('docente_id')
