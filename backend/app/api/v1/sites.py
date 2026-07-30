"""Locais, beacons e redes Wi-Fi.

Define o que conta como "estar no hangar". O cadastro e do painel; o
`location-config` e consumido pelo app do funcionario.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import (
    CurrentAdmin,
    CurrentPrincipal,
    SessionDep,
    TenantRepo,
    require_roles,
)
from app.models import Beacon, Site, WifiNetwork
from app.models.enums import AuditAction, UserRole
from app.schemas.location import (
    BeaconConfig,
    BeaconCreate,
    BeaconList,
    BeaconSummary,
    BeaconUpdate,
    LocationConfig,
    SiteCreate,
    SiteDetail,
    SiteList,
    SiteSummary,
    SiteUpdate,
    WifiConfig,
    WifiNetworkCreate,
    WifiNetworkList,
    WifiNetworkSummary,
    WifiNetworkUpdate,
)
from app.services import audit
from app.services import location as location_service

router = APIRouter(prefix="/sites", tags=["locais"])

ESCRITA = [Depends(require_roles(UserRole.OWNER, UserRole.HR))]


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _site_or_404(repo: TenantRepo, site_id: uuid.UUID) -> Site:
    site = await repo.get(Site, site_id)
    if site is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Local nao encontrado"
        )
    return site


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


# --------------------------------------------------------------------------
# Sites
# --------------------------------------------------------------------------


@router.get("", response_model=SiteList)
async def list_sites(
    _: CurrentPrincipal,
    repo: TenantRepo,
    only_active: bool = Query(default=False),
) -> SiteList:
    """Locais da empresa.

    Aberto tambem ao app: o funcionario precisa saber quais locais existem
    para buscar a configuracao de deteccao de cada um.
    """
    query = repo.query(Site).order_by(Site.name)
    if only_active:
        query = query.where(Site.is_active.is_(True))

    result = await repo.session.execute(query)
    sites = list(result.scalars().all())

    return SiteList(
        items=[SiteSummary.model_validate(site) for site in sites],
        total=len(sites),
    )


@router.post(
    "", response_model=SiteDetail, status_code=status.HTTP_201_CREATED, dependencies=ESCRITA
)
async def create_site(
    payload: SiteCreate,
    principal: CurrentAdmin,
    repo: TenantRepo,
    session: SessionDep,
    request: Request,
) -> SiteDetail:
    try:
        site = await location_service.create_site(repo, payload)
    except location_service.DuplicateError as exc:
        raise _conflict(exc) from exc

    await audit.record_for(
        session,
        principal,
        action=AuditAction.CREATE,
        entity_type="site",
        entity_id=site.id,
        description=f"Local {site.name} cadastrado",
        ip_address=_client_ip(request),
    )

    return await _site_detail(session, site)


@router.get("/{site_id}", response_model=SiteDetail)
async def get_site(
    site_id: uuid.UUID, _: CurrentAdmin, repo: TenantRepo, session: SessionDep
) -> SiteDetail:
    site = await _site_or_404(repo, site_id)
    return await _site_detail(session, site)


@router.patch("/{site_id}", response_model=SiteDetail, dependencies=ESCRITA)
async def update_site(
    site_id: uuid.UUID,
    payload: SiteUpdate,
    principal: CurrentAdmin,
    repo: TenantRepo,
    session: SessionDep,
    request: Request,
) -> SiteDetail:
    site = await _site_or_404(repo, site_id)

    try:
        await location_service.update_site(repo, site, payload)
    except location_service.DuplicateError as exc:
        raise _conflict(exc) from exc
    except location_service.LocationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await audit.record_for(
        session,
        principal,
        action=AuditAction.UPDATE,
        entity_type="site",
        entity_id=site.id,
        payload={"campos": sorted(payload.model_dump(exclude_unset=True).keys())},
        ip_address=_client_ip(request),
    )

    return await _site_detail(session, site)


# --------------------------------------------------------------------------
# Beacons
# --------------------------------------------------------------------------


@router.get("/{site_id}/beacons", response_model=BeaconList)
async def list_beacons(
    site_id: uuid.UUID,
    _: CurrentAdmin,
    repo: TenantRepo,
    only_active: bool = Query(default=False),
) -> BeaconList:
    await _site_or_404(repo, site_id)
    beacons = await location_service.list_beacons(repo, site_id, only_active=only_active)
    return BeaconList(
        items=[BeaconSummary.model_validate(beacon) for beacon in beacons],
        total=len(beacons),
    )


@router.post(
    "/{site_id}/beacons",
    response_model=BeaconSummary,
    status_code=status.HTTP_201_CREATED,
    dependencies=ESCRITA,
)
async def create_beacon(
    site_id: uuid.UUID,
    payload: BeaconCreate,
    principal: CurrentAdmin,
    repo: TenantRepo,
    session: SessionDep,
    request: Request,
) -> BeaconSummary:
    site = await _site_or_404(repo, site_id)

    try:
        beacon = await location_service.create_beacon(repo, site, payload)
    except location_service.DuplicateError as exc:
        raise _conflict(exc) from exc

    await audit.record_for(
        session,
        principal,
        action=AuditAction.CREATE,
        entity_type="beacon",
        entity_id=beacon.id,
        payload={"protocolo": beacon.protocol.value, "local": site.name},
        description=f"Beacon {beacon.label} cadastrado",
        ip_address=_client_ip(request),
    )

    return BeaconSummary.model_validate(beacon)


@router.patch(
    "/{site_id}/beacons/{beacon_id}", response_model=BeaconSummary, dependencies=ESCRITA
)
async def update_beacon(
    site_id: uuid.UUID,
    beacon_id: uuid.UUID,
    payload: BeaconUpdate,
    principal: CurrentAdmin,
    repo: TenantRepo,
    session: SessionDep,
    request: Request,
) -> BeaconSummary:
    await _site_or_404(repo, site_id)

    beacon = await repo.get(Beacon, beacon_id)
    if beacon is None or beacon.site_id != site_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Beacon nao encontrado"
        )

    await location_service.update_beacon(repo, beacon, payload)

    await audit.record_for(
        session,
        principal,
        action=AuditAction.UPDATE,
        entity_type="beacon",
        entity_id=beacon.id,
        payload={"campos": sorted(payload.model_dump(exclude_unset=True).keys())},
        ip_address=_client_ip(request),
    )

    return BeaconSummary.model_validate(beacon)


# --------------------------------------------------------------------------
# Redes Wi-Fi
# --------------------------------------------------------------------------


@router.get("/{site_id}/wifi-networks", response_model=WifiNetworkList)
async def list_wifi(
    site_id: uuid.UUID,
    _: CurrentAdmin,
    repo: TenantRepo,
    only_active: bool = Query(default=False),
) -> WifiNetworkList:
    await _site_or_404(repo, site_id)
    networks = await location_service.list_wifi(repo, site_id, only_active=only_active)
    return WifiNetworkList(
        items=[WifiNetworkSummary.model_validate(net) for net in networks],
        total=len(networks),
    )


@router.post(
    "/{site_id}/wifi-networks",
    response_model=WifiNetworkSummary,
    status_code=status.HTTP_201_CREATED,
    dependencies=ESCRITA,
)
async def create_wifi(
    site_id: uuid.UUID,
    payload: WifiNetworkCreate,
    principal: CurrentAdmin,
    repo: TenantRepo,
    session: SessionDep,
    request: Request,
) -> WifiNetworkSummary:
    site = await _site_or_404(repo, site_id)

    try:
        network = await location_service.create_wifi(repo, site, payload)
    except location_service.DuplicateError as exc:
        raise _conflict(exc) from exc

    await audit.record_for(
        session,
        principal,
        action=AuditAction.CREATE,
        entity_type="wifi_network",
        entity_id=network.id,
        payload={"ssid": network.ssid, "local": site.name},
        ip_address=_client_ip(request),
    )

    return WifiNetworkSummary.model_validate(network)


@router.patch(
    "/{site_id}/wifi-networks/{network_id}",
    response_model=WifiNetworkSummary,
    dependencies=ESCRITA,
)
async def update_wifi(
    site_id: uuid.UUID,
    network_id: uuid.UUID,
    payload: WifiNetworkUpdate,
    principal: CurrentAdmin,
    repo: TenantRepo,
    session: SessionDep,
    request: Request,
) -> WifiNetworkSummary:
    await _site_or_404(repo, site_id)

    network = await repo.get(WifiNetwork, network_id)
    if network is None or network.site_id != site_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Rede nao encontrada"
        )

    try:
        await location_service.update_wifi(repo, network, payload)
    except location_service.DuplicateError as exc:
        raise _conflict(exc) from exc

    await audit.record_for(
        session,
        principal,
        action=AuditAction.UPDATE,
        entity_type="wifi_network",
        entity_id=network.id,
        ip_address=_client_ip(request),
    )

    return WifiNetworkSummary.model_validate(network)


# --------------------------------------------------------------------------
# Configuracao para o app
# --------------------------------------------------------------------------


@router.get("/{site_id}/location-config", response_model=LocationConfig)
async def location_config(
    site_id: uuid.UUID,
    _: CurrentPrincipal,
    repo: TenantRepo,
) -> LocationConfig:
    """O que o app precisa para reconhecer o local.

    Aberto ao app do funcionario, e nao so ao painel. Os identificadores aqui
    nao sao segredo e nao teriam como ser: advertisement BLE e transmissao
    publica, legivel por qualquer aparelho ao alcance com um app de varredura
    comum. Esconde-los do app nao atrapalharia quem ja esteve no hangar uma
    vez — so o uso legitimo. A defesa contra fraude e rosto, liveness e
    auditoria.

    Traz apenas o que esta ativo: um beacon desativado no painel deve parar de
    ser procurado assim que o app atualizar o cache.
    """
    site = await _site_or_404(repo, site_id)

    beacons = await location_service.list_beacons(repo, site_id, only_active=True)
    networks = await location_service.list_wifi(repo, site_id, only_active=True)

    return LocationConfig(
        site_id=site.id,
        site_name=site.name,
        latitude=site.latitude,
        longitude=site.longitude,
        geofence_radius_m=site.geofence_radius_m,
        timezone=site.timezone,
        beacons=[BeaconConfig.model_validate(beacon) for beacon in beacons],
        wifi_networks=[WifiConfig.model_validate(net) for net in networks],
        config_version=location_service.config_version(site, beacons, networks),
    )


async def _site_detail(session: SessionDep, site: Site) -> SiteDetail:
    detail = SiteDetail.model_validate(site)
    detail.beacon_count, detail.wifi_count = await location_service.count_children(
        session, site
    )
    return detail
