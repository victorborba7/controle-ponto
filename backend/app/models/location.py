"""Locais fisicos e os sinais que provam presenca neles.

Tres tabelas que alimentam a cadeia de fallback beacon -> Wi-Fi -> GPS:
Site (o local), Beacon (sinal BLE) e WifiNetwork (rede da empresa).
"""

import uuid

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import enum_column
from app.models.enums import BeaconProtocol


class Site(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Unidade da empresa — no MVP, o hangar."""

    __tablename__ = "sites"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_sites_tenant_name"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(String(400), nullable=True)

    # Centro do geofence, usado no ultimo elo da cadeia (GPS).
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geofence_radius_m: Mapped[int] = mapped_column(Integer, nullable=False, default=150)

    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="America/Sao_Paulo")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    beacons: Mapped[list["Beacon"]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )
    wifi_networks: Mapped[list["WifiNetwork"]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Site {self.name}>"


class Beacon(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Beacon BLE instalado no local — elo mais forte da cadeia.

    Guarda iBeacon e Eddystone lado a lado porque a escolha do hardware ainda
    depende do risco R1: o iOS nao entrega advertisement de iBeacon via
    CoreBluetooth (so via CoreLocation, com UUID conhecido de antemao), entao
    o formato pode acabar sendo Eddystone. O backend nao precisa esperar
    essa decisao — os campos nao usados ficam nulos.
    """

    __tablename__ = "beacons"
    __table_args__ = (
        Index("ix_beacons_tenant_site", "tenant_id", "site_id", "is_active"),
        # Um mesmo beacon fisico nao pode ser cadastrado duas vezes no tenant.
        UniqueConstraint(
            "tenant_id",
            "protocol",
            "ibeacon_uuid",
            "ibeacon_major",
            "ibeacon_minor",
            "eddystone_namespace",
            "eddystone_instance",
            name="uq_beacons_tenant_identifier",
        ),
    )

    site_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Onde o beacon esta fisicamente: "Hangar - Portao A", "Almoxarifado".
    label: Mapped[str] = mapped_column(String(200), nullable=False)

    protocol: Mapped[BeaconProtocol] = mapped_column(
        enum_column(BeaconProtocol, "beacon_protocol", length=20),
        nullable=False,
    )

    # --- iBeacon ---
    ibeacon_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ibeacon_major: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ibeacon_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Eddystone ---
    eddystone_namespace: Mapped[str | None] = mapped_column(String(20), nullable=True)
    eddystone_instance: Mapped[str | None] = mapped_column(String(12), nullable=True)

    mac_address: Mapped[str | None] = mapped_column(String(17), nullable=True)

    # Limiar de proximidade. RSSI e negativo e quanto mais perto, maior (menos
    # negativo): -70 dBm equivale a poucos metros. Detectar o beacon do outro
    # lado da rua nao pode contar como presenca.
    min_rssi: Mapped[int] = mapped_column(Integer, nullable=False, default=-80)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    site: Mapped["Site"] = relationship(back_populates="beacons")

    def __repr__(self) -> str:
        return f"<Beacon {self.label} ({self.protocol})>"


class WifiNetwork(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Rede Wi-Fi da empresa — elo intermediario da cadeia.

    O BSSID (MAC do access point) e o que vale: identifica o ponto de acesso
    fisico. SSID e so o nome da rede e qualquer um cria um hotspot com o mesmo
    nome, por isso um match so por SSID vale menos confianca (ver Etapa 6).
    """

    __tablename__ = "wifi_networks"
    __table_args__ = (
        Index("ix_wifi_tenant_site", "tenant_id", "site_id", "is_active"),
        UniqueConstraint("tenant_id", "bssid", name="uq_wifi_tenant_bssid"),
    )

    site_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
    )
    ssid: Mapped[str] = mapped_column(String(64), nullable=False)
    # Normalizado em minusculas com dois-pontos: "a4:2b:8c:00:11:22".
    bssid: Mapped[str | None] = mapped_column(String(17), nullable=True)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    site: Mapped["Site"] = relationship(back_populates="wifi_networks")

    def __repr__(self) -> str:
        return f"<WifiNetwork {self.ssid}>"
