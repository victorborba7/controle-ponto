"""Popula o banco com dados de exemplo para desenvolvimento.

    docker compose exec api python -m app.db.seed

Idempotente: rodar duas vezes nao duplica nada. Nao cria embedding facial —
isso depende da engine da Etapa 3 e do enrollment da Etapa 4.
"""

import asyncio
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models import (
    Beacon,
    BeaconProtocol,
    Employee,
    EmployeeStatus,
    Site,
    Tenant,
    User,
    UserRole,
    WifiNetwork,
)

TENANT_SLUG = "empresa-demo"
DEMO_PASSWORD = "senha123"


async def seed(session: AsyncSession) -> None:
    existing = await session.scalar(select(Tenant).where(Tenant.slug == TENANT_SLUG))
    if existing is not None:
        print(f"Tenant '{TENANT_SLUG}' ja existe — nada a fazer.")
        return

    tenant = Tenant(
        name="Empresa Demo Ltda",
        slug=TENANT_SLUG,
        cnpj="12.345.678/0001-90",
    )
    session.add(tenant)
    await session.flush()  # atribui tenant.id para as FKs abaixo

    admin = User(
        tenant_id=tenant.id,
        email="rh@empresademo.com.br",
        password_hash=hash_password(DEMO_PASSWORD),
        name="Maria do RH",
        role=UserRole.OWNER,
    )
    session.add(admin)

    # Coordenadas de exemplo (regiao de Guarulhos/SP). Trocar pelas reais do
    # hangar quando o mapeamento fisico for feito (Etapa 5).
    site = Site(
        tenant_id=tenant.id,
        name="Hangar Principal",
        address="Av. Monteiro Lobato, 1000 - Guarulhos/SP",
        latitude=-23.4356,
        longitude=-46.4731,
        geofence_radius_m=200,
    )
    session.add(site)
    await session.flush()

    session.add_all(
        [
            # Dois protocolos de proposito: a escolha do hardware ainda depende
            # do risco R1 (iOS x iBeacon), e o seed exercita os dois caminhos.
            Beacon(
                tenant_id=tenant.id,
                site_id=site.id,
                label="Hangar - Portao A",
                protocol=BeaconProtocol.IBEACON,
                ibeacon_uuid="f7826da6-4fa2-4e98-8024-bc5b71e0893e",
                ibeacon_major=1,
                ibeacon_minor=1,
                min_rssi=-75,
            ),
            Beacon(
                tenant_id=tenant.id,
                site_id=site.id,
                label="Hangar - Almoxarifado",
                protocol=BeaconProtocol.EDDYSTONE,
                eddystone_namespace="edd1ebeac04e5defa017",
                eddystone_instance="000000000001",
                min_rssi=-80,
            ),
        ]
    )

    session.add(
        WifiNetwork(
            tenant_id=tenant.id,
            site_id=site.id,
            ssid="EmpresaDemo-Corp",
            bssid="a4:2b:8c:00:11:22",
            label="AP do hangar",
        )
    )

    session.add_all(
        [
            Employee(
                tenant_id=tenant.id,
                external_code="0001",
                name="Joao da Silva",
                cpf="123.456.789-00",
                job_title="Mecanico de Aeronaves",
                password_hash=hash_password(DEMO_PASSWORD),
                status=EmployeeStatus.ACTIVE,
                hired_at=date(2024, 3, 1),
                default_site_id=site.id,
            ),
            Employee(
                tenant_id=tenant.id,
                external_code="0002",
                name="Ana Souza",
                cpf="987.654.321-00",
                job_title="Inspetora de Qualidade",
                password_hash=hash_password(DEMO_PASSWORD),
                status=EmployeeStatus.ACTIVE,
                hired_at=date(2023, 9, 15),
                default_site_id=site.id,
            ),
        ]
    )

    await session.commit()

    print("Seed concluido:")
    print(f"  tenant......: {tenant.name} (slug: {tenant.slug})")
    print(f"  admin.......: {admin.email} / {DEMO_PASSWORD}")
    print(f"  site........: {site.name}")
    print("  beacons.....: 2 (1 iBeacon, 1 Eddystone)")
    print("  wifi........: 1")
    print(f"  funcionarios: 0001 e 0002 / {DEMO_PASSWORD}")


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await seed(session)


if __name__ == "__main__":
    asyncio.run(main())
