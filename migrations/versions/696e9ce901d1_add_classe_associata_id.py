"""Add classe_associata_id

Revision ID: 696e9ce901d1
Revises: a0a49502cae5
Create Date: 2026-01-23 16:50:28.583196
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '696e9ce901d1'
down_revision = 'a0a49502cae5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('classe', schema=None) as batch_op:
        batch_op.add_column(sa.Column('classe_associata_id', sa.Integer(), nullable=True))
        # 🔥 IMPORTANTE: niente foreign key per SQLite


def downgrade():
    with op.batch_alter_table('classe', schema=None) as batch_op:
        # niente drop_constraint perché non è stata creata
        batch_op.drop_column('classe_associata_id')
