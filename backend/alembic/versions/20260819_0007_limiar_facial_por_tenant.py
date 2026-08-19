"""Limiar de reconhecimento facial por tenant

NULL nas duas colunas significa "usa o padrao global de settings" — que e o
estado de toda empresa ja cadastrada. Nenhuma decisao de ponto muda por esta
migracao.

Revision ID: 0007_limiar_por_tenant
Revises: 0006_login_attempts
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_limiar_por_tenant"
down_revision: str | None = "0006_login_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("face_match_threshold", sa.Float(), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("face_review_threshold", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "face_review_threshold")
    op.drop_column("tenants", "face_match_threshold")
