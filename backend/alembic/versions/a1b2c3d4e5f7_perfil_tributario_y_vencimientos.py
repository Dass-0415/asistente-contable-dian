"""perfil tributario y vencimientos manuales

Revision ID: a1b2c3d4e5f7
Revises: f1b2c3d4e5f6
Create Date: 2026-09-16 14:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "f1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('empresas', sa.Column('periodicidad_iva', sa.String(length=20), nullable=False, server_default='bimestral'))
    op.add_column('empresas', sa.Column('agente_retencion', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('empresas', sa.Column('obligado_renta', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('empresas', sa.Column('obligado_exogena', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('empresas', sa.Column('obligado_ica', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('empresas', sa.Column('municipio_ica', sa.String(length=120), nullable=True))
    op.create_table(
        'vencimientos_tributarios',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('empresa_id', sa.String(length=36), nullable=False),
        sa.Column('obligacion', sa.String(length=120), nullable=False),
        sa.Column('periodo', sa.String(length=80), nullable=True),
        sa.Column('fecha_vencimiento', sa.Date(), nullable=False),
        sa.Column('jurisdiccion', sa.String(length=120), nullable=True),
        sa.Column('fuente', sa.String(length=300), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_vencimientos_tributarios_empresa_id', 'vencimientos_tributarios', ['empresa_id'], unique=False)
    op.create_index('ix_vencimientos_tributarios_fecha_vencimiento', 'vencimientos_tributarios', ['fecha_vencimiento'], unique=False)
    op.create_index('ix_vencimiento_empresa_fecha', 'vencimientos_tributarios', ['empresa_id', 'fecha_vencimiento'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_vencimiento_empresa_fecha', table_name='vencimientos_tributarios')
    op.drop_index('ix_vencimientos_tributarios_fecha_vencimiento', table_name='vencimientos_tributarios')
    op.drop_index('ix_vencimientos_tributarios_empresa_id', table_name='vencimientos_tributarios')
    op.drop_table('vencimientos_tributarios')
    op.drop_column('empresas', 'municipio_ica')
    op.drop_column('empresas', 'obligado_ica')
    op.drop_column('empresas', 'obligado_exogena')
    op.drop_column('empresas', 'obligado_renta')
    op.drop_column('empresas', 'agente_retencion')
    op.drop_column('empresas', 'periodicidad_iva')
