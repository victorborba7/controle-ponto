"""Regras de cadastro de locais, beacons e redes Wi-Fi."""

import hashlib
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import TenantRepository
from app.models import Beacon, Site, WifiNetwork
from app.models.enums import BeaconProtocol
from app.schemas.location import (
    BeaconCreate,
    BeaconUpdate,
    SiteCreate,
    SiteUpdate,
    WifiNetworkCreate,
    WifiNetworkUpdate,
)
from app.services.location_validator import SiteRegistry


class LocationError(Exception):
    """Falha de regra de negocio no cadastro de locais."""


class DuplicateError(LocationError):
    pass


class NotFoundError(LocationError):
    pass


# --------------------------------------------------------------------------
# Sites
# --------------------------------------------------------------------------


async def create_site(repo: TenantRepository, payload: SiteCreate) -> Site:
    if await _site_by_name(repo, payload.name) is not None:
        raise DuplicateError(f"Ja existe um local chamado {payload.name!r}")

    site = Site(**payload.model_dump())
    repo.add(site)
    await repo.flush()
    return site


async def update_site(repo: TenantRepository, site: Site, payload: SiteUpdate) -> Site:
    changes = payload.model_dump(exclude_unset=True)

    if "name" in changes:
        existing = await _site_by_name(repo, changes["name"])
        if existing is not None and existing.id != site.id:
            raise DuplicateError(f"Ja existe um local chamado {changes['name']!r}")

    for field, value in changes.items():
        setattr(site, field, value)

    _ensure_coordinates_paired(site)
    await repo.flush()
    return site


def _ensure_coordinates_paired(site: Site) -> None:
    """Latitude sem longitude nao localiza nada.

    Checado tambem aqui, e nao so no schema: uma atualizacao parcial pode
    limpar so um dos dois campos e deixar o site num estado que o schema de
    criacao nunca permitiria.
    """
    if (site.latitude is None) != (site.longitude is None):
        raise LocationError("Informe latitude e longitude juntas, ou nenhuma das duas")


async def _site_by_name(repo: TenantRepository, name: str) -> Site | None:
    return await repo.session.scalar(repo.query(Site).where(Site.name == name).limit(1))


async def get_site_or_raise(repo: TenantRepository, site_id: uuid.UUID) -> Site:
    site = await repo.get(Site, site_id)
    if site is None:
        raise NotFoundError("Local nao encontrado")
    return site


# --------------------------------------------------------------------------
# Beacons
# --------------------------------------------------------------------------


async def create_beacon(
    repo: TenantRepository, site: Site, payload: BeaconCreate
) -> Beacon:
    """Cadastra um beacon no local.

    A duplicidade e checada aqui antes de chegar ao banco para devolver ao RH
    uma mensagem util — o indice unico ainda protege, mas o erro dele nao diz
    qual beacon ja existia.
    """
    duplicado = await _find_duplicate_beacon(repo, payload)
    if duplicado is not None:
        raise DuplicateError(
            f"Este identificador ja esta cadastrado no beacon {duplicado.label!r}"
        )

    beacon = Beacon(site_id=site.id, **payload.model_dump())
    repo.add(beacon)
    await repo.flush()
    return beacon


async def _find_duplicate_beacon(
    repo: TenantRepository, payload: BeaconCreate
) -> Beacon | None:
    query = repo.query(Beacon).where(Beacon.protocol == payload.protocol)

    if payload.protocol is BeaconProtocol.EDDYSTONE:
        query = query.where(
            Beacon.eddystone_namespace == payload.eddystone_namespace,
            Beacon.eddystone_instance == payload.eddystone_instance,
        )
    elif payload.protocol is BeaconProtocol.IBEACON:
        query = query.where(
            Beacon.ibeacon_uuid == payload.ibeacon_uuid,
            Beacon.ibeacon_major == payload.ibeacon_major,
            Beacon.ibeacon_minor == payload.ibeacon_minor,
        )
    else:
        query = query.where(Beacon.mac_address == payload.mac_address)

    return await repo.session.scalar(query.limit(1))


async def update_beacon(
    repo: TenantRepository, beacon: Beacon, payload: BeaconUpdate
) -> Beacon:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(beacon, field, value)
    await repo.flush()
    return beacon


async def list_beacons(
    repo: TenantRepository, site_id: uuid.UUID, *, only_active: bool = False
) -> list[Beacon]:
    query = repo.query(Beacon).where(Beacon.site_id == site_id)
    if only_active:
        query = query.where(Beacon.is_active.is_(True))

    result = await repo.session.execute(query.order_by(Beacon.label))
    return list(result.scalars().all())


# --------------------------------------------------------------------------
# Redes Wi-Fi
# --------------------------------------------------------------------------


async def create_wifi(
    repo: TenantRepository, site: Site, payload: WifiNetworkCreate
) -> WifiNetwork:
    if payload.bssid is not None:
        existing = await repo.session.scalar(
            repo.query(WifiNetwork).where(WifiNetwork.bssid == payload.bssid).limit(1)
        )
        if existing is not None:
            raise DuplicateError(
                f"O BSSID {payload.bssid} ja esta cadastrado na rede {existing.ssid!r}"
            )

    network = WifiNetwork(site_id=site.id, **payload.model_dump())
    repo.add(network)
    await repo.flush()
    return network


async def update_wifi(
    repo: TenantRepository, network: WifiNetwork, payload: WifiNetworkUpdate
) -> WifiNetwork:
    changes = payload.model_dump(exclude_unset=True)

    if changes.get("bssid") is not None:
        existing = await repo.session.scalar(
            repo.query(WifiNetwork).where(WifiNetwork.bssid == changes["bssid"]).limit(1)
        )
        if existing is not None and existing.id != network.id:
            raise DuplicateError(f"O BSSID {changes['bssid']} ja esta cadastrado")

    for field, value in changes.items():
        setattr(network, field, value)

    await repo.flush()
    return network


async def list_wifi(
    repo: TenantRepository, site_id: uuid.UUID, *, only_active: bool = False
) -> list[WifiNetwork]:
    query = repo.query(WifiNetwork).where(WifiNetwork.site_id == site_id)
    if only_active:
        query = query.where(WifiNetwork.is_active.is_(True))

    result = await repo.session.execute(query.order_by(WifiNetwork.ssid))
    return list(result.scalars().all())


# --------------------------------------------------------------------------
# Contagens e versao da configuracao
# --------------------------------------------------------------------------


async def count_children(session: AsyncSession, site: Site) -> tuple[int, int]:
    """Quantos beacons e redes ativos o local tem."""
    beacons = await session.scalar(
        select(func.count())
        .select_from(Beacon)
        .where(Beacon.site_id == site.id, Beacon.is_active.is_(True))
    )
    networks = await session.scalar(
        select(func.count())
        .select_from(WifiNetwork)
        .where(WifiNetwork.site_id == site.id, WifiNetwork.is_active.is_(True))
    )
    return (beacons or 0), (networks or 0)


async def load_registry(repo: TenantRepository) -> SiteRegistry:
    """Retrato do cadastro da empresa, para a cadeia de validacao decidir.

    Carregado de uma vez, e nao consultado elo a elo: sao poucas dezenas de
    linhas mesmo numa empresa grande, e uma unica ida ao banco por batida e
    melhor que tres. E o que permite a cadeia ser uma funcao pura.
    """
    sites = await repo.session.execute(repo.query(Site))
    beacons = await repo.session.execute(repo.query(Beacon))
    networks = await repo.session.execute(repo.query(WifiNetwork))

    return SiteRegistry(
        sites=tuple(sites.scalars().all()),
        beacons=tuple(beacons.scalars().all()),
        wifi_networks=tuple(networks.scalars().all()),
    )


def config_version(
    site: Site, beacons: list[Beacon], networks: list[WifiNetwork]
) -> str:
    """Identificador curto que muda quando a configuracao muda.

    Derivado do instante da ultima alteracao de qualquer peca. Permite ao app
    perguntar "mudou algo?" sem baixar e comparar a configuracao inteira — o
    que importa num hangar onde a conexao e ruim.
    """
    timestamps: list[datetime] = [site.updated_at]
    timestamps.extend(beacon.updated_at for beacon in beacons)
    timestamps.extend(network.updated_at for network in networks)

    # A contagem entra no calculo porque remover um item nao muda o instante
    # mais recente dos que sobraram.
    seed = f"{max(timestamps).isoformat()}|{len(beacons)}|{len(networks)}"
    return hashlib.sha256(seed.encode()).hexdigest()[:16]
