"""Aggiunte data_inizio e data_fine a Classe

Revision ID: ced5d0db3bfd
Revises: a40d675bbf22
Create Date: 2026-01-14 10:51:16.665625

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ced5d0db3bfd'
down_revision = 'a40d675bbf22'
branch_labels = None
depends_on = None


def upgrade():
    # --- CLASSE ---
    with op.batch_alter_table('classe', schema=None) as batch_op:
        batch_op.add_column(sa.Column('data_inizio', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('data_fine', sa.Date(), nullable=True))
        batch_op.alter_column(
            'giorni_lezione',
            existing_type=sa.VARCHAR(length=50),
            type_=sa.String(length=100),
            existing_nullable=True
        )

    # --- GIORNO FISSO ---
    with op.batch_alter_table('giorno_fisso', schema=None) as batch_op:
        batch_op.alter_column(
            'docente_id',
            existing_type=sa.INTEGER(),
            nullable=False
        )
        batch_op.create_foreign_key(
            'fk_giorno_fisso_docente',
            'docente',
            ['docente_id'],
            ['id']
        )

    # --- GIORNO SPECIALE ---
    with op.batch_alter_table('giorno_speciale', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_giorno_speciale_docente',
            'docente',
            ['docente_id'],
            ['id']
        )


def downgrade():
    # --- GIORNO SPECIALE ---
    with op.batch_alter_table('giorno_speciale', schema=None) as batch_op:
        batch_op.drop_constraint('fk_giorno_speciale_docente', type_='foreignkey')

    # --- GIORNO FISSO ---
    with op.batch_alter_table('giorno_fisso', schema=None) as batch_op:
        batch_op.drop_constraint('fk_giorno_fisso_docente', type_='foreignkey')
        batch_op.alter_column(
            'docente_id',
            existing_type=sa.INTEGER(),
            nullable=True
        )

    # --- CLASSE ---
    with op.batch_alter_table('classe', schema=None) as batch_op:
        batch_op.alter_column(
            'giorni_lezione',
            existing_type=sa.String(length=100),
            type_=sa.VARCHAR(length=50),
            existing_nullable=True
        )
        batch_op.drop_column('data_fine')
        batch_op.drop_column('data_inizio')
