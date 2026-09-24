"""historial estructurado de RUT por empresa

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f7
Create Date: 2026-09-22 17:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ruts_empresa",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("empresa_id", sa.String(length=36), nullable=False),
        sa.Column("archivo_nombre", sa.String(length=300), nullable=True),
        sa.Column("archivo_sha256", sa.String(length=64), nullable=False),
        sa.Column("numero_formulario", sa.String(length=40), nullable=True),
        sa.Column("nit_detectado", sa.String(length=30), nullable=True),
        sa.Column("dv_detectado", sa.String(length=2), nullable=True),
        sa.Column("tipo_persona_detectado", sa.String(length=20), nullable=True),
        sa.Column("direccion_seccional", sa.String(length=160), nullable=True),
        sa.Column("municipio", sa.String(length=160), nullable=True),
        sa.Column("fecha_generacion", sa.Date(), nullable=True),
        sa.Column("actividades_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("responsabilidades_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("fuente_extraccion", sa.String(length=20), nullable=False, server_default="pdf_texto"),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("analizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("aplicado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ruts_empresa_empresa_id", "ruts_empresa", ["empresa_id"], unique=False)
    op.create_index("ix_ruts_empresa_archivo_sha256", "ruts_empresa", ["archivo_sha256"], unique=False)
    op.create_index("ix_rut_empresa_activo", "ruts_empresa", ["empresa_id", "activo"], unique=False)
    op.create_index("ix_rut_empresa_analizado", "ruts_empresa", ["empresa_id", "analizado_en"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_rut_empresa_analizado", table_name="ruts_empresa")
    op.drop_index("ix_rut_empresa_activo", table_name="ruts_empresa")
    op.drop_index("ix_ruts_empresa_archivo_sha256", table_name="ruts_empresa")
    op.drop_index("ix_ruts_empresa_empresa_id", table_name="ruts_empresa")
    op.drop_table("ruts_empresa")
