"""O que o app reporta sobre onde esta.

Estes schemas sao a fronteira entre o aparelho e a decisao do servidor. O app
**relata o que observou**, nunca conclui: quem decide se aquilo prova presenca
e o servidor, porque o app roda no celular do proprio funcionario e nao e uma
fonte confiavel de veredito.
"""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import BeaconProtocol
from app.schemas.location import (
    Bssid,
    EddystoneInstance,
    EddystoneNamespace,
    IBeaconUuid,
)
from app.services.identifiers import MAX_RSSI_LIMIT, MIN_RSSI_LIMIT

# Quantos beacons/redes o app pode reportar de uma vez. Um hangar tem poucos
# beacons; um payload com centenas e tentativa de sobrecarregar a validacao.
MAX_BEACON_READINGS = 30
MAX_WIFI_READINGS = 30


class BeaconReading(BaseModel):
    """Um beacon detectado pela varredura BLE."""

    model_config = ConfigDict(extra="forbid")

    protocol: BeaconProtocol = BeaconProtocol.EDDYSTONE

    eddystone_namespace: EddystoneNamespace | None = None
    eddystone_instance: EddystoneInstance | None = None

    ibeacon_uuid: IBeaconUuid | None = None
    ibeacon_major: int | None = Field(default=None, ge=0, le=65535)
    ibeacon_minor: int | None = Field(default=None, ge=0, le=65535)

    mac_address: Bssid | None = None

    rssi: int = Field(ge=MIN_RSSI_LIMIT, le=MAX_RSSI_LIMIT)

    @model_validator(mode="after")
    def identificador_presente(self) -> Self:
        if self.protocol is BeaconProtocol.EDDYSTONE:
            if not (self.eddystone_namespace and self.eddystone_instance):
                raise ValueError("Leitura Eddystone exige namespace e instance")
        elif self.protocol is BeaconProtocol.IBEACON:
            if not (
                self.ibeacon_uuid
                and self.ibeacon_major is not None
                and self.ibeacon_minor is not None
            ):
                raise ValueError("Leitura iBeacon exige uuid, major e minor")
        elif not self.mac_address:
            raise ValueError("Leitura por MAC exige o endereco")
        return self

    @property
    def identity(self) -> tuple:
        """Chave de comparacao com o cadastro.

        Ja normalizada pelos tipos anotados, entao a comparacao e exata e nao
        depende da grafia que o sistema operacional reportou.
        """
        if self.protocol is BeaconProtocol.EDDYSTONE:
            return (self.protocol, self.eddystone_namespace, self.eddystone_instance)
        if self.protocol is BeaconProtocol.IBEACON:
            return (
                self.protocol,
                self.ibeacon_uuid,
                self.ibeacon_major,
                self.ibeacon_minor,
            )
        return (self.protocol, self.mac_address)


class WifiReading(BaseModel):
    """A rede Wi-Fi a que o aparelho esta conectado (ou que enxergou)."""

    model_config = ConfigDict(extra="forbid")

    ssid: str = Field(min_length=1, max_length=64)
    # Opcional porque o iOS so entrega o BSSID com a entitlement de acesso a
    # informacao de Wi-Fi (risco R2), e no Android depende de permissao de
    # localizacao. Sem ele a evidencia vale bem menos.
    bssid: Bssid | None = None


class GpsReading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    # Raio de incerteza em metros que o proprio sistema operacional reporta.
    # E o que separa "estou aqui" de "estou em algum lugar deste bairro".
    accuracy_m: float = Field(ge=0, le=100_000)


class LocationEvidence(BaseModel):
    """Tudo que o app observou no momento da batida.

    Os tres canais chegam juntos, e nao um por vez: assim o servidor escolhe o
    melhor disponivel e ainda consegue cruzar os sinais para detectar
    incoerencia — um beacon do hangar visto de outra cidade, por exemplo.
    """

    model_config = ConfigDict(extra="forbid")

    beacons: list[BeaconReading] = Field(default_factory=list, max_length=MAX_BEACON_READINGS)
    wifi: list[WifiReading] = Field(default_factory=list, max_length=MAX_WIFI_READINGS)
    gps: GpsReading | None = None
    # Horario do aparelho. Guardado para auditoria, nunca usado para decidir —
    # o relogio do celular e ajustavel pelo proprio funcionario.
    captured_at: datetime | None = None
