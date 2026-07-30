"""Corrige a unicidade de beacons: indice parcial por protocolo

A restricao anterior cobria todas as colunas de identificador de uma vez
(tenant, protocol, ibeacon_*, eddystone_*) e nao funcionava: no Postgres, NULL
e distinto de qualquer outro NULL em restricao de unicidade. Dois beacons
Eddystone identicos passavam, porque as colunas de iBeacon eram nulas nos dois
e as linhas eram consideradas diferentes.

Verificado na pratica antes da correcao: dois INSERTs com o mesmo
namespace/instance foram ambos aceitos.

Revision ID: 0003_beacon_unique
Revises: 0002_initial_schema
Create Date: 2026-07-30

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0003_beacon_unique"
down_revision: str | None = "0002_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_beacons_tenant_identifier", "beacons", type_="unique")

    op.create_index(
        "uq_beacons_eddystone",
        "beacons",
        ["tenant_id", "eddystone_namespace", "eddystone_instance"],
        unique=True,
        postgresql_where="protocol = 'eddystone'",
    )
    op.create_index(
        "uq_beacons_ibeacon",
        "beacons",
        ["tenant_id", "ibeacon_uuid", "ibeacon_major", "ibeacon_minor"],
        unique=True,
        postgresql_where="protocol = 'ibeacon'",
    )


def downgrade() -> None:
    op.drop_index("uq_beacons_ibeacon", table_name="beacons")
    op.drop_index("uq_beacons_eddystone", table_name="beacons")
    op.create_unique_constraint(
        "uq_beacons_tenant_identifier",
        "beacons",
        [
            "tenant_id",
            "protocol",
            "ibeacon_uuid",
            "ibeacon_major",
            "ibeacon_minor",
            "eddystone_namespace",
            "eddystone_instance",
        ],
    )
