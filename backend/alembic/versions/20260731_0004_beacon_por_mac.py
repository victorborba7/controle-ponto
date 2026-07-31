"""Permite identificar beacon pelo endereco MAC

Terceiro modo de identificacao, para hardware que transmite formato
proprietario que nao sabemos interpretar — o MAC e o unico identificador que
sempre existe num anuncio BLE.

Segue o mesmo cuidado da migracao 0003: indice parcial, e nao restricao sobre
todas as colunas. No Postgres, NULL e distinto de qualquer outro NULL em
restricao de unicidade, entao uma restricao ampla nao impediria duplicatas.

Revision ID: 0004_beacon_mac
Revises: 0003_beacon_unique
Create Date: 2026-07-31

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0004_beacon_mac"
down_revision: str | None = "0003_beacon_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_beacons_mac",
        "beacons",
        ["tenant_id", "mac_address"],
        unique=True,
        postgresql_where="protocol = 'mac'",
    )


def downgrade() -> None:
    op.drop_index("uq_beacons_mac", table_name="beacons")
