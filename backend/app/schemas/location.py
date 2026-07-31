"""Schemas de locais, beacons e redes Wi-Fi."""

import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.models.enums import BeaconProtocol
from app.services.identifiers import (
    MAX_RSSI_LIMIT,
    MIN_RSSI_LIMIT,
    normalize_bssid,
    normalize_eddystone_instance,
    normalize_eddystone_namespace,
    normalize_ibeacon_uuid,
    validate_timezone,
)

# Tipos que ja chegam normalizados ao servico — o resto do sistema nunca
# precisa lembrar de converter.
Timezone = Annotated[str, AfterValidator(validate_timezone)]
Bssid = Annotated[str, AfterValidator(normalize_bssid)]
EddystoneNamespace = Annotated[str, AfterValidator(normalize_eddystone_namespace)]
EddystoneInstance = Annotated[str, AfterValidator(normalize_eddystone_instance)]
IBeaconUuid = Annotated[str, AfterValidator(normalize_ibeacon_uuid)]


# --------------------------------------------------------------------------
# Site
# --------------------------------------------------------------------------


class SiteCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    address: str | None = Field(default=None, max_length=400)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    # 10 m e menor que a imprecisao tipica de GPS de celular, o que rejeitaria
    # quem esta de fato no local; 5 km ja abrange um bairro e nao prova nada.
    geofence_radius_m: int = Field(default=150, ge=10, le=5000)
    timezone: Timezone = "America/Sao_Paulo"

    @model_validator(mode="after")
    def coordenadas_completas(self) -> Self:
        """Latitude sem longitude nao localiza nada."""
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Informe latitude e longitude juntas, ou nenhuma das duas")
        return self


class SiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    address: str | None = Field(default=None, max_length=400)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    geofence_radius_m: int | None = Field(default=None, ge=10, le=5000)
    timezone: Timezone | None = None
    is_active: bool | None = None


class SiteSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    geofence_radius_m: int
    timezone: str
    is_active: bool


class SiteDetail(SiteSummary):
    beacon_count: int = 0
    wifi_count: int = 0
    created_at: datetime


class SiteList(BaseModel):
    items: list[SiteSummary]
    total: int


# --------------------------------------------------------------------------
# Beacon
# --------------------------------------------------------------------------


class BeaconCreate(BaseModel):
    """Cadastro de um beacon.

    Os campos de iBeacon e Eddystone convivem porque o modelo suporta os dois,
    mas cada beacon usa apenas um conjunto: o validador exige o do protocolo
    escolhido e recusa o do outro, para nao gravar registro pela metade.
    """

    label: str = Field(
        min_length=2,
        max_length=200,
        description='Onde o beacon esta, em linguagem humana: "Hangar - Portao A"',
    )
    protocol: BeaconProtocol = BeaconProtocol.EDDYSTONE

    eddystone_namespace: EddystoneNamespace | None = None
    eddystone_instance: EddystoneInstance | None = None

    ibeacon_uuid: IBeaconUuid | None = None
    ibeacon_major: int | None = Field(default=None, ge=0, le=65535)
    ibeacon_minor: int | None = Field(default=None, ge=0, le=65535)

    mac_address: Bssid | None = None
    min_rssi: int = Field(default=-80, ge=MIN_RSSI_LIMIT, le=MAX_RSSI_LIMIT)

    @model_validator(mode="after")
    def identificador_coerente_com_o_protocolo(self) -> Self:
        tem_eddystone = any((self.eddystone_namespace, self.eddystone_instance))
        tem_ibeacon = any((self.ibeacon_uuid, self.ibeacon_major, self.ibeacon_minor))

        if self.protocol is BeaconProtocol.EDDYSTONE:
            faltando = [
                nome
                for nome, valor in (
                    ("eddystone_namespace", self.eddystone_namespace),
                    ("eddystone_instance", self.eddystone_instance),
                )
                if valor is None
            ]
            if faltando:
                raise ValueError(f"Beacon Eddystone exige {' e '.join(faltando)}")
            if tem_ibeacon:
                raise ValueError(
                    "Beacon Eddystone nao deve receber campos de iBeacon. "
                    "Confira o protocolo selecionado."
                )
            return self

        if self.protocol is BeaconProtocol.IBEACON:
            if (
                self.ibeacon_uuid is None
                or self.ibeacon_major is None
                or self.ibeacon_minor is None
            ):
                raise ValueError("Beacon iBeacon exige uuid, major e minor")
            if tem_eddystone:
                raise ValueError(
                    "Beacon iBeacon nao deve receber campos de Eddystone. "
                    "Confira o protocolo selecionado."
                )
            return self

        # MAC
        if self.mac_address is None:
            raise ValueError(
                "Beacon identificado por MAC exige o endereco. Use a tela de "
                "diagnostico do app para descobri-lo."
            )
        if tem_eddystone or tem_ibeacon:
            raise ValueError(
                "Beacon identificado por MAC nao deve receber campos de "
                "Eddystone nem de iBeacon. Confira o protocolo selecionado."
            )
        return self


class BeaconUpdate(BaseModel):
    """Atualizacao parcial.

    O identificador nao esta aqui de proposito: trocar o que identifica o
    beacon e trocar de beacon. Cadastre o novo e desative o antigo, para o
    historico de pontos continuar apontando para o hardware certo.
    """

    label: str | None = Field(default=None, min_length=2, max_length=200)
    mac_address: Bssid | None = None
    min_rssi: int | None = Field(default=None, ge=MIN_RSSI_LIMIT, le=MAX_RSSI_LIMIT)
    is_active: bool | None = None


class BeaconSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    site_id: uuid.UUID
    label: str
    protocol: BeaconProtocol
    eddystone_namespace: str | None = None
    eddystone_instance: str | None = None
    ibeacon_uuid: str | None = None
    ibeacon_major: int | None = None
    ibeacon_minor: int | None = None
    mac_address: str | None = None
    min_rssi: int
    is_active: bool


class BeaconList(BaseModel):
    items: list[BeaconSummary]
    total: int


# --------------------------------------------------------------------------
# Rede Wi-Fi
# --------------------------------------------------------------------------


class WifiNetworkCreate(BaseModel):
    ssid: str = Field(min_length=1, max_length=64)
    # Opcional, mas e o campo que importa: SSID e so o nome da rede e qualquer
    # um cria um hotspot com o mesmo nome. O BSSID identifica o ponto de acesso
    # fisico, e por isso vale mais confianca na Etapa 6.
    bssid: Bssid | None = None
    label: str | None = Field(default=None, max_length=200)


class WifiNetworkUpdate(BaseModel):
    ssid: str | None = Field(default=None, min_length=1, max_length=64)
    bssid: Bssid | None = None
    label: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None


class WifiNetworkSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    site_id: uuid.UUID
    ssid: str
    bssid: str | None = None
    label: str | None = None
    is_active: bool


class WifiNetworkList(BaseModel):
    items: list[WifiNetworkSummary]
    total: int


# --------------------------------------------------------------------------
# Configuracao para o app
# --------------------------------------------------------------------------


class BeaconConfig(BaseModel):
    """Beacon como o app precisa conhece-lo.

    Sem o `label`: o nome interno da area nao serve para o app e e informacao
    sobre a planta da empresa que nao precisa sair do painel.

    O `mac_address` vem justamente para o app poder filtrar: numa varredura
    aberta ele ve dezenas de aparelhos alheios, e so deve relatar ao servidor
    os que estao cadastrados. Sem esta lista, relatar MAC significaria enviar
    identificadores de celulares e relogios de terceiros.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    protocol: BeaconProtocol
    eddystone_namespace: str | None = None
    eddystone_instance: str | None = None
    ibeacon_uuid: str | None = None
    ibeacon_major: int | None = None
    ibeacon_minor: int | None = None
    mac_address: str | None = None
    min_rssi: int


class WifiConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ssid: str
    bssid: str | None = None


class LocationConfig(BaseModel):
    """O que o app baixa e cacheia para reconhecer o local.

    **Estes identificadores nao sao segredo, e nao ha como serem.** Um
    advertisement BLE e uma transmissao publica: qualquer aparelho ao alcance
    consegue le-lo com um aplicativo de varredura comum. Esconder o namespace
    do app nao dificultaria nada para quem ja esteve no hangar uma vez —
    apenas atrapalharia o uso legitimo. A defesa contra fraude e a combinacao
    de rosto, liveness e trilha de auditoria, nunca o sigilo do identificador.
    """

    site_id: uuid.UUID
    site_name: str
    latitude: float | None = None
    longitude: float | None = None
    geofence_radius_m: int
    timezone: str
    beacons: list[BeaconConfig]
    wifi_networks: list[WifiConfig]
    # Muda sempre que qualquer parte da configuracao muda, para o app saber se
    # o cache dele envelheceu sem precisar comparar tudo.
    config_version: str
