"""aprendizaje, retenciones contables y relación de notas

Revision ID: d2e4f6a8b001
Revises: c7a1f2b63055
Create Date: 2026-09-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d2e4f6a8b001"
down_revision: Union[str, None] = "c7a1f2b63055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("facturas") as batch:
        batch.add_column(sa.Column("retenciones_contables_json", sa.Text(), nullable=True))
        batch.add_column(sa.Column("documento_origen_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("relacion_documento_confianza", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("relacion_documento_motivo", sa.Text(), nullable=True))
    op.create_index("ix_facturas_documento_origen_id", "facturas", ["documento_origen_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_facturas_documento_origen_id", table_name="facturas")
    with op.batch_alter_table("facturas") as batch:
        batch.drop_column("relacion_documento_motivo")
        batch.drop_column("relacion_documento_confianza")
        batch.drop_column("documento_origen_id")
        batch.drop_column("retenciones_contables_json")
