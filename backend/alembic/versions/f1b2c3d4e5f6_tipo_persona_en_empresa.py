"""tipo_persona en empresa para distinguir natural y juridica

Revision ID: f1b2c3d4e5f6
Revises: d2e4f6a8b001
Create Date: 2026-09-16 13:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1b2c3d4e5f6"
down_revision: Union[str, None] = "d2e4f6a8b001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('empresas', sa.Column('tipo_persona', sa.String(length=20), nullable=False, server_default='juridica'))
    op.execute("UPDATE empresas SET tipo_persona='juridica' WHERE tipo_persona IS NULL")
    # Se conserva el default de servidor para compatibilidad con SQLite y PostgreSQL.


def downgrade() -> None:
    op.drop_column('empresas', 'tipo_persona')
