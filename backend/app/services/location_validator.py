"""Cadeia de validacao de presenca: beacon -> Wi-Fi -> GPS.

Decide se o funcionario esta no local e, principalmente, **registra como foi
decidido**. Cada elo prova menos que o anterior, e o registro guarda qual deles
sustentou a batida — e o que permite ao RH pesar um ponto contestado meses
depois, em vez de ter apenas "aprovado" sem explicacao.

    beacon   presenca fisica em uma area especifica    confianca alta
    Wi-Fi    conectado a um AP da empresa              confianca media
    GPS      dentro do raio do endereco                confianca baixa
    nenhum   nao prova nada                            vai para revisao

**Este modulo e uma funcao pura sobre um retrato do cadastro.** Nao toca banco,
nao le relogio, nao chama rede. Toda a regra fica exercitavel em teste de mesa,
inclusive as fronteiras que sao caras de reproduzir no hangar: sinal fraco, GPS
impreciso, sinais que se contradizem.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.models import Beacon, Site, WifiNetwork
from app.models.enums import BeaconProtocol, LocationMethod
from app.schemas.evidence import BeaconReading, GpsReading, LocationEvidence, WifiReading
from app.services.geo import haversine_distance_m

# --------------------------------------------------------------------------
# Confianca por metodo
# --------------------------------------------------------------------------
# Os numeros expressam quao dificil e forjar cada evidencia:
#
# - Beacon exige estar ao alcance de um radio de curto alcance instalado no
#   local. Forjavel por quem se der o trabalho de transmitir um advertisement
#   falso, mas precisa conhecer o identificador — o que exige ter estado la.
# - Wi-Fi por BSSID exige estar ao alcance do ponto de acesso fisico. O MAC e
#   clonavel, e por isso vale menos que o beacon.
# - Wi-Fi so por SSID quase nao prova nada: qualquer celular cria um hotspot
#   com o nome que quiser.
# - GPS e o mais fraco: coordenada e falsificavel por app de mock location sem
#   nenhum conhecimento previo, e ainda erra muito dentro de um galpao.

BEACON_CONFIDENCE_FLOOR = 0.75
BEACON_CONFIDENCE_CEILING = 0.95
# Margem de sinal, em dB acima do limiar, para a confianca chegar ao teto.
BEACON_FULL_MARGIN_DB = 20

WIFI_BSSID_CONFIDENCE = 0.70
WIFI_SSID_ONLY_CONFIDENCE = 0.35

GPS_CONFIDENCE_FLOOR = 0.20
GPS_CONFIDENCE_CEILING = 0.55

# Acima disto o circulo de incerteza engole o local e a leitura nao diz nada,
# mesmo que o centro caia dentro do raio.
GPS_MAX_ACCURACY_FACTOR = 3.0
GPS_MAX_ACCURACY_M = 1_000.0

# Folga antes de chamar o GPS de incoerente com o beacon. Precisa ser generosa:
# GPS dentro de galpao metalico erra dezenas ou centenas de metros com
# facilidade — que e justamente por que os beacons existem. Erro dessa ordem e
# esperado; quilometros de distancia nao sao.
GPS_INCONSISTENCY_MARGIN_M = 5_000.0


@dataclass(frozen=True)
class SiteRegistry:
    """Retrato do que esta cadastrado, para a cadeia decidir sem tocar o banco.

    Carregado uma vez por requisicao (ver `load_registry`). Manter a cadeia
    ignorante de banco e o que torna cada ramo testavel de mesa.
    """

    sites: tuple[Site, ...]
    beacons: tuple[Beacon, ...]
    wifi_networks: tuple[WifiNetwork, ...]

    def site_by_id(self, site_id: uuid.UUID) -> Site | None:
        return next((site for site in self.sites if site.id == site_id), None)


@dataclass(frozen=True)
class LocationVerdict:
    """O que a cadeia concluiu, e por que.

    Descritivo de proposito: informa o metodo, a confianca e as ressalvas, mas
    nao decide o destino do ponto. Essa decisao e da Etapa 7, que combina isto
    com o resultado do reconhecimento facial.
    """

    method: LocationMethod
    confidence: float
    accepted: bool
    reason: str

    site_id: uuid.UUID | None = None
    site_name: str | None = None
    beacon_id: uuid.UUID | None = None
    beacon_rssi: int | None = None
    wifi_network_id: uuid.UUID | None = None
    distance_to_site_m: float | None = None
    gps_accuracy_m: float | None = None

    #: Sinais que se contradizem. Nao reprovam sozinhos, mas sao motivo para o
    #: RH conferir — ver `_detect_inconsistencies`.
    inconsistencies: tuple[str, ...] = ()

    #: Observacoes sobre evidencia que quase valeu (beacon visto porem fraco,
    #: GPS impreciso demais). E o que explica ao funcionario por que o ponto
    #: caiu em revisao.
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def needs_review(self) -> bool:
        return not self.accepted or bool(self.inconsistencies)


# --------------------------------------------------------------------------
# Cadeia
# --------------------------------------------------------------------------


def validate_location(
    evidence: LocationEvidence, registry: SiteRegistry
) -> LocationVerdict:
    """Percorre os elos do mais forte ao mais fraco e para no primeiro que valer.

    Para no primeiro sucesso em vez de somar evidencias: se o beacon confirma,
    a leitura de GPS nao acrescenta nada — e no hangar ela seria justamente a
    mais ruim das tres. O que os elos restantes ainda fazem e servir de
    contraprova, no cruzamento de incoerencias.
    """
    notes: list[str] = []

    for elo in (_check_beacons, _check_wifi, _check_gps):
        veredito = elo(evidence, registry, notes)
        if veredito is not None:
            inconsistencies = _detect_inconsistencies(veredito, evidence, registry)
            return _with(veredito, notes=tuple(notes), inconsistencies=inconsistencies)

    return LocationVerdict(
        method=LocationMethod.NONE,
        confidence=0.0,
        accepted=False,
        reason=_reason_for_no_signal(evidence, notes),
        notes=tuple(notes),
    )


def _with(veredito: LocationVerdict, **changes: Any) -> LocationVerdict:
    from dataclasses import replace

    return replace(veredito, **changes)


# --------------------------------------------------------------------------
# Elo 1 — beacon
# --------------------------------------------------------------------------


def _check_beacons(
    evidence: LocationEvidence, registry: SiteRegistry, notes: list[str]
) -> LocationVerdict | None:
    """Beacon cadastrado e com sinal acima do limiar.

    Entre varios beacons validos vence o de sinal mais forte, que e o mais
    proximo — importa quando areas vizinhas se sobrepoem e as duas sao vistas
    ao mesmo tempo.
    """
    ativos = {
        _beacon_identity(beacon): beacon
        for beacon in registry.beacons
        if beacon.is_active
    }

    melhor: tuple[BeaconReading, Beacon] | None = None
    fracos: list[str] = []

    for leitura in evidence.beacons:
        cadastrado = ativos.get(leitura.identity)
        if cadastrado is None:
            continue

        if leitura.rssi < cadastrado.min_rssi:
            # Detectado, mas de longe demais para confirmar presenca. Nao serve
            # como prova, mas explica ao funcionario o que aconteceu.
            fracos.append(
                f"{cadastrado.label} visto com sinal {leitura.rssi} dBm, "
                f"abaixo do minimo de {cadastrado.min_rssi} dBm"
            )
            continue

        if melhor is None or leitura.rssi > melhor[0].rssi:
            melhor = (leitura, cadastrado)

    notes.extend(fracos)

    if melhor is None:
        return None

    leitura, beacon = melhor
    site = registry.site_by_id(beacon.site_id)

    return LocationVerdict(
        method=LocationMethod.BEACON,
        confidence=_beacon_confidence(leitura.rssi, beacon.min_rssi),
        accepted=True,
        reason=f"Beacon {beacon.label} detectado a {leitura.rssi} dBm",
        site_id=beacon.site_id,
        site_name=site.name if site else None,
        beacon_id=beacon.id,
        beacon_rssi=leitura.rssi,
    )


def _beacon_identity(beacon: Beacon) -> tuple:
    """Chave de comparacao, espelhando `BeaconReading.identity`.

    As duas precisam produzir a mesma tupla para o mesmo hardware — se
    divergirem, o beacon simplesmente nunca casa, sem erro nenhum.
    """
    if beacon.protocol is BeaconProtocol.EDDYSTONE:
        return (beacon.protocol, beacon.eddystone_namespace, beacon.eddystone_instance)
    if beacon.protocol is BeaconProtocol.IBEACON:
        return (
            beacon.protocol,
            beacon.ibeacon_uuid,
            beacon.ibeacon_major,
            beacon.ibeacon_minor,
        )
    return (beacon.protocol, beacon.mac_address)


def _beacon_confidence(rssi: int, min_rssi: int) -> float:
    """Cresce com a folga de sinal sobre o limiar.

    Exatamente no limiar a confianca fica no piso: o funcionario esta no limite
    da area, e um passo para tras ja o tiraria dela.
    """
    margem = max(0, rssi - min_rssi)
    fracao = min(1.0, margem / BEACON_FULL_MARGIN_DB)
    faixa = BEACON_CONFIDENCE_CEILING - BEACON_CONFIDENCE_FLOOR
    return round(BEACON_CONFIDENCE_FLOOR + faixa * fracao, 4)


# --------------------------------------------------------------------------
# Elo 2 — Wi-Fi
# --------------------------------------------------------------------------


def _check_wifi(
    evidence: LocationEvidence, registry: SiteRegistry, notes: list[str]
) -> LocationVerdict | None:
    """Rede da empresa.

    Match por BSSID vale bem mais que por SSID: o BSSID e o MAC do ponto de
    acesso fisico, enquanto o SSID e so o nome da rede — qualquer celular cria
    um hotspot chamado "EmpresaDemo-Corp" em dez segundos.
    """
    ativas = [rede for rede in registry.wifi_networks if rede.is_active]

    por_bssid = {rede.bssid: rede for rede in ativas if rede.bssid}
    por_ssid: dict[str, WifiNetwork] = {}
    for rede in ativas:
        por_ssid.setdefault(rede.ssid, rede)

    candidata_por_ssid: tuple[WifiReading, WifiNetwork] | None = None

    for leitura in evidence.wifi:
        if leitura.bssid and (rede := por_bssid.get(leitura.bssid)):
            site = registry.site_by_id(rede.site_id)
            return LocationVerdict(
                method=LocationMethod.WIFI,
                confidence=WIFI_BSSID_CONFIDENCE,
                accepted=True,
                reason=f"Conectado ao ponto de acesso {rede.ssid} ({rede.bssid})",
                site_id=rede.site_id,
                site_name=site.name if site else None,
                wifi_network_id=rede.id,
            )

        if candidata_por_ssid is None and (rede := por_ssid.get(leitura.ssid)):
            candidata_por_ssid = (leitura, rede)

    if candidata_por_ssid is None:
        return None

    leitura, rede = candidata_por_ssid

    # Se a rede tem BSSID cadastrado e o aparelho reportou outro, isto nao e
    # "faltou informacao": e um AP diferente se dizendo a rede da empresa.
    if rede.bssid and leitura.bssid and leitura.bssid != rede.bssid:
        notes.append(
            f"Rede {leitura.ssid} vista em um ponto de acesso desconhecido "
            f"({leitura.bssid})"
        )
        return None

    site = registry.site_by_id(rede.site_id)
    notes.append("Rede reconhecida apenas pelo nome; o ponto de acesso nao foi confirmado")

    return LocationVerdict(
        method=LocationMethod.WIFI,
        confidence=WIFI_SSID_ONLY_CONFIDENCE,
        accepted=True,
        reason=f"Conectado a rede {rede.ssid}, sem confirmacao do ponto de acesso",
        site_id=rede.site_id,
        site_name=site.name if site else None,
        wifi_network_id=rede.id,
    )


# --------------------------------------------------------------------------
# Elo 3 — GPS
# --------------------------------------------------------------------------


def _check_gps(
    evidence: LocationEvidence, registry: SiteRegistry, notes: list[str]
) -> LocationVerdict | None:
    """Ultimo recurso: dentro do raio do endereco cadastrado."""
    gps = evidence.gps
    if gps is None:
        return None

    localizaveis = [
        site
        for site in registry.sites
        if site.is_active and site.latitude is not None and site.longitude is not None
    ]
    if not localizaveis:
        notes.append("Nenhum local tem coordenadas cadastradas")
        return None

    melhor: tuple[Site, float] | None = None
    for site in localizaveis:
        distancia = haversine_distance_m(
            gps.latitude, gps.longitude, site.latitude, site.longitude
        )
        if melhor is None or distancia < melhor[1]:
            melhor = (site, distancia)

    site, distancia = melhor
    limite_de_precisao = min(
        GPS_MAX_ACCURACY_M, site.geofence_radius_m * GPS_MAX_ACCURACY_FACTOR
    )

    if gps.accuracy_m > limite_de_precisao:
        # O circulo de incerteza e maior que o proprio local: mesmo o centro
        # caindo dentro do raio, a leitura nao distingue "no hangar" de
        # "no bairro do hangar".
        notes.append(
            f"Localizacao imprecisa demais (+/- {gps.accuracy_m:.0f} m) para "
            f"confirmar presenca em {site.name}"
        )
        return None

    # Distancia otimista: o ponto mais proximo do local em que o aparelho ainda
    # poderia estar, dada a incerteza. Beneficia quem esta de fato no lugar,
    # que e o caso comum — o ponto duvidoso vai para revisao, nao para recusa.
    distancia_otimista = max(0.0, distancia - gps.accuracy_m)

    if distancia_otimista > site.geofence_radius_m:
        notes.append(
            f"A {distancia:.0f} m de {site.name}, fora do raio de "
            f"{site.geofence_radius_m} m"
        )
        return None

    return LocationVerdict(
        method=LocationMethod.GPS,
        confidence=_gps_confidence(distancia_otimista, gps, site.geofence_radius_m),
        accepted=True,
        reason=(
            f"A {distancia:.0f} m de {site.name} (+/- {gps.accuracy_m:.0f} m), "
            f"dentro do raio de {site.geofence_radius_m} m"
        ),
        site_id=site.id,
        site_name=site.name,
        distance_to_site_m=round(distancia, 1),
        gps_accuracy_m=gps.accuracy_m,
    )


def _gps_confidence(distancia: float, gps: GpsReading, raio: int) -> float:
    """Cai com a distancia ate o centro e com a imprecisao da leitura.

    Os dois fatores pesam igual: estar no centro com leitura ruim e estar na
    borda com leitura boa sao igualmente inconclusivos.
    """
    fator_posicao = 1.0 - min(1.0, distancia / raio)
    fator_precisao = 1.0 - min(1.0, gps.accuracy_m / raio)
    combinado = 0.5 * fator_posicao + 0.5 * fator_precisao

    faixa = GPS_CONFIDENCE_CEILING - GPS_CONFIDENCE_FLOOR
    return round(GPS_CONFIDENCE_FLOOR + faixa * combinado, 4)


# --------------------------------------------------------------------------
# Cruzamento de sinais
# --------------------------------------------------------------------------


def _detect_inconsistencies(
    veredito: LocationVerdict, evidence: LocationEvidence, registry: SiteRegistry
) -> tuple[str, ...]:
    """Sinais que se contradizem.

    O caso concreto que isto pega: alguem em casa transmitindo um advertissement
    falso com o identificador do beacon do hangar. O beacon "confirma", mas o
    GPS aponta outra cidade — e essa contradicao e o que denuncia a farsa.

    A folga e deliberadamente grande. GPS dentro de galpao metalico erra
    dezenas ou centenas de metros com facilidade, e e exatamente por isso que os
    beacons existem; tratar esse erro como fraude reprovaria gente honesta. Uma
    divergencia de quilometros, porem, nao e erro de multipercurso.
    """
    if veredito.method is LocationMethod.GPS or evidence.gps is None:
        return ()
    if veredito.site_id is None:
        return ()

    site = registry.site_by_id(veredito.site_id)
    if site is None or site.latitude is None or site.longitude is None:
        return ()

    gps = evidence.gps
    distancia = haversine_distance_m(
        gps.latitude, gps.longitude, site.latitude, site.longitude
    )
    limite = site.geofence_radius_m + gps.accuracy_m + GPS_INCONSISTENCY_MARGIN_M

    if distancia <= limite:
        return ()

    return (
        f"O sinal indica {site.name}, mas a localizacao do aparelho esta a "
        f"{distancia / 1000:.1f} km dali",
    )


def build_audit_payload(
    evidence: LocationEvidence, veredito: LocationVerdict
) -> dict[str, Any]:
    """Retrato do que o app viu e do que a cadeia concluiu, para o `location_raw`.

    Guarda **tudo** que foi observado, e nao so o sinal que venceu: um ponto
    contestado meses depois so pode ser reavaliado se as leituras descartadas
    tambem estiverem la. Sem isso, a unica resposta possivel a "por que fui
    reprovado?" seria "o sistema disse que sim".

    A regra de decisao muda com o tempo (limiar recalibrado, beacon movido de
    lugar), entao a conclusao registrada tambem entra: e o que valia na epoca.
    """
    return {
        "observado": {
            "beacons": [
                {
                    "protocol": leitura.protocol.value,
                    "eddystone_namespace": leitura.eddystone_namespace,
                    "eddystone_instance": leitura.eddystone_instance,
                    "ibeacon_uuid": leitura.ibeacon_uuid,
                    "ibeacon_major": leitura.ibeacon_major,
                    "ibeacon_minor": leitura.ibeacon_minor,
                    "mac_address": leitura.mac_address,
                    "rssi": leitura.rssi,
                }
                for leitura in evidence.beacons
            ],
            "wifi": [
                {"ssid": leitura.ssid, "bssid": leitura.bssid} for leitura in evidence.wifi
            ],
            "gps": (
                {
                    "latitude": evidence.gps.latitude,
                    "longitude": evidence.gps.longitude,
                    "accuracy_m": evidence.gps.accuracy_m,
                }
                if evidence.gps
                else None
            ),
            "captured_at": (
                evidence.captured_at.isoformat() if evidence.captured_at else None
            ),
        },
        "conclusao": {
            "method": veredito.method.value,
            "confidence": veredito.confidence,
            "accepted": veredito.accepted,
            "reason": veredito.reason,
            "site_id": str(veredito.site_id) if veredito.site_id else None,
            "distance_to_site_m": veredito.distance_to_site_m,
            "inconsistencies": list(veredito.inconsistencies),
            "notes": list(veredito.notes),
        },
    }


def _reason_for_no_signal(evidence: LocationEvidence, notes: list[str]) -> str:
    """Explica a ausencia de prova em linguagem util para o RH.

    Distingue dois casos que exigem providencias diferentes: "o aparelho nao
    captou nada" costuma ser permissao negada ou Bluetooth desligado, enquanto
    "captou, mas nada bate" aponta para cadastro faltando ou beacon fora do ar.
    """
    if notes:
        return "Nenhum sinal confirmou a presenca. " + "; ".join(notes)

    observado = []
    if evidence.beacons:
        observado.append(f"{len(evidence.beacons)} beacon(s) desconhecido(s)")
    if evidence.wifi:
        observado.append(f"{len(evidence.wifi)} rede(s) nao cadastrada(s)")

    if not observado:
        return (
            "O aparelho nao reportou nenhum sinal de localizacao. "
            "Verifique as permissoes de Bluetooth e localizacao no celular."
        )

    if evidence.gps is None:
        observado.append("localizacao indisponivel")

    return "Nenhum sinal confirmou a presenca: " + ", ".join(observado)
