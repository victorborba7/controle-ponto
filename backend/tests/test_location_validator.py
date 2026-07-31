"""Cadeia de validacao de presenca.

Testes de mesa: nenhum banco, nenhuma rede. A cadeia e uma funcao pura sobre um
retrato do cadastro, e e por isso que as fronteiras caras de reproduzir no
hangar — sinal no limite, GPS impreciso, sinais que se contradizem — cabem numa
suite que roda em milissegundos.
"""

import uuid

import pytest

from app.models import Beacon, Site, WifiNetwork
from app.models.enums import BeaconProtocol, LocationMethod
from app.schemas.evidence import BeaconReading, GpsReading, LocationEvidence, WifiReading
from app.services.geo import haversine_distance_m
from app.services.location_validator import (
    SiteRegistry,
    build_audit_payload,
    validate_location,
)

TENANT = uuid.uuid4()

# Coordenadas de referencia (regiao de Guarulhos/SP).
HANGAR_LAT, HANGAR_LON = -23.4356, -46.4731

NAMESPACE = "edd1ebeac04e5defa017"
INSTANCE_PORTAO = "000000000001"
INSTANCE_ALMOXARIFADO = "000000000002"


# --------------------------------------------------------------------------
# Montagem do cenario
# --------------------------------------------------------------------------


def make_site(
    *,
    name: str = "Hangar Principal",
    latitude: float | None = HANGAR_LAT,
    longitude: float | None = HANGAR_LON,
    radius: int = 200,
    is_active: bool = True,
) -> Site:
    site = Site(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        name=name,
        latitude=latitude,
        longitude=longitude,
        geofence_radius_m=radius,
        timezone="America/Sao_Paulo",
        is_active=is_active,
    )
    return site


def make_beacon(
    site: Site,
    *,
    label: str = "Portao A",
    instance: str = INSTANCE_PORTAO,
    min_rssi: int = -75,
    is_active: bool = True,
) -> Beacon:
    return Beacon(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        site_id=site.id,
        label=label,
        protocol=BeaconProtocol.EDDYSTONE,
        eddystone_namespace=NAMESPACE,
        eddystone_instance=instance,
        min_rssi=min_rssi,
        is_active=is_active,
    )


def make_beacon_mac(
    site: Site,
    *,
    label: str = "Aruba - Portao A",
    mac: str = "7c:ec:79:44:c5:b5",
    min_rssi: int = -75,
) -> Beacon:
    return Beacon(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        site_id=site.id,
        label=label,
        protocol=BeaconProtocol.MAC,
        mac_address=mac,
        min_rssi=min_rssi,
        is_active=True,
    )


def make_wifi(
    site: Site,
    *,
    ssid: str = "EmpresaDemo-Corp",
    bssid: str | None = "a4:2b:8c:00:11:22",
    is_active: bool = True,
) -> WifiNetwork:
    return WifiNetwork(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        site_id=site.id,
        ssid=ssid,
        bssid=bssid,
        is_active=is_active,
    )


def registry(
    sites: list[Site], beacons: list[Beacon] = (), wifi: list[WifiNetwork] = ()
) -> SiteRegistry:
    return SiteRegistry(
        sites=tuple(sites), beacons=tuple(beacons), wifi_networks=tuple(wifi)
    )


def beacon_reading(instance: str = INSTANCE_PORTAO, rssi: int = -60) -> BeaconReading:
    return BeaconReading(
        protocol=BeaconProtocol.EDDYSTONE,
        eddystone_namespace=NAMESPACE,
        eddystone_instance=instance,
        rssi=rssi,
    )


def coord_a_metros(metros: float) -> tuple[float, float]:
    """Coordenada a `metros` ao norte do hangar.

    Um grau de latitude vale ~111.320 m em qualquer lugar do globo, o que
    torna o deslocamento norte-sul o jeito mais previsivel de posicionar um
    ponto a uma distancia conhecida.
    """
    return (HANGAR_LAT + metros / 111_320.0, HANGAR_LON)


# --------------------------------------------------------------------------
# Os quatro desfechos — o criterio de pronto da etapa
# --------------------------------------------------------------------------


def test_beacon_confirma_presenca():
    site = make_site()
    reg = registry([site], [make_beacon(site)])

    veredito = validate_location(LocationEvidence(beacons=[beacon_reading()]), reg)

    assert veredito.method is LocationMethod.BEACON
    assert veredito.accepted
    assert veredito.site_id == site.id
    assert veredito.beacon_rssi == -60
    assert veredito.confidence >= 0.75
    assert not veredito.needs_review


def test_wifi_confirma_quando_nao_ha_beacon():
    site = make_site()
    reg = registry([site], [make_beacon(site)], [make_wifi(site)])

    veredito = validate_location(
        LocationEvidence(wifi=[WifiReading(ssid="EmpresaDemo-Corp", bssid="a4:2b:8c:00:11:22")]),
        reg,
    )

    assert veredito.method is LocationMethod.WIFI
    assert veredito.accepted
    assert veredito.confidence == 0.70


def test_gps_confirma_quando_nao_ha_beacon_nem_wifi():
    site = make_site()
    lat, lon = coord_a_metros(50)
    reg = registry([site], [make_beacon(site)], [make_wifi(site)])

    veredito = validate_location(
        LocationEvidence(gps=GpsReading(latitude=lat, longitude=lon, accuracy_m=15)), reg
    )

    assert veredito.method is LocationMethod.GPS
    assert veredito.accepted
    assert veredito.distance_to_site_m == pytest.approx(50, abs=2)


def test_sem_sinal_nenhum_vai_para_revisao():
    site = make_site()
    reg = registry([site], [make_beacon(site)], [make_wifi(site)])

    veredito = validate_location(LocationEvidence(), reg)

    assert veredito.method is LocationMethod.NONE
    assert not veredito.accepted
    assert veredito.confidence == 0.0
    assert veredito.needs_review
    # A mensagem separa "nada foi captado" de "captou, mas nada bate": a
    # primeira aponta para permissao negada, a segunda para cadastro faltando.
    assert "nao reportou nenhum sinal" in veredito.reason
    assert "permissoes" in veredito.reason


def test_sinais_captados_mas_nenhum_cadastrado():
    """Distinto do caso acima: aqui ha o que investigar no cadastro."""
    site = make_site()
    reg = registry([site], [make_beacon(site)])

    veredito = validate_location(
        LocationEvidence(
            beacons=[beacon_reading("00000000ffff", rssi=-40)],
            wifi=[WifiReading(ssid="Vizinho", bssid="11:22:33:44:55:66")],
        ),
        reg,
    )

    assert veredito.method is LocationMethod.NONE
    assert "desconhecido" in veredito.reason
    assert "nao cadastrada" in veredito.reason


# --------------------------------------------------------------------------
# Ordem da cadeia
# --------------------------------------------------------------------------


def test_beacon_tem_precedencia_sobre_wifi_e_gps():
    """Confirmado o elo mais forte, os demais nao acrescentam nada."""
    site = make_site()
    lat, lon = coord_a_metros(50)
    reg = registry([site], [make_beacon(site)], [make_wifi(site)])

    veredito = validate_location(
        LocationEvidence(
            beacons=[beacon_reading()],
            wifi=[WifiReading(ssid="EmpresaDemo-Corp", bssid="a4:2b:8c:00:11:22")],
            gps=GpsReading(latitude=lat, longitude=lon, accuracy_m=10),
        ),
        reg,
    )

    assert veredito.method is LocationMethod.BEACON


def test_wifi_tem_precedencia_sobre_gps():
    site = make_site()
    lat, lon = coord_a_metros(50)
    reg = registry([site], [], [make_wifi(site)])

    veredito = validate_location(
        LocationEvidence(
            wifi=[WifiReading(ssid="EmpresaDemo-Corp", bssid="a4:2b:8c:00:11:22")],
            gps=GpsReading(latitude=lat, longitude=lon, accuracy_m=10),
        ),
        reg,
    )

    assert veredito.method is LocationMethod.WIFI


def test_confianca_decresce_ao_longo_da_cadeia():
    """A ordem dos elos reflete quao dificil e forjar cada evidencia."""
    site = make_site()
    lat, lon = coord_a_metros(50)
    reg = registry([site], [make_beacon(site)], [make_wifi(site)])

    por_beacon = validate_location(LocationEvidence(beacons=[beacon_reading()]), reg)
    por_wifi = validate_location(
        LocationEvidence(wifi=[WifiReading(ssid="EmpresaDemo-Corp", bssid="a4:2b:8c:00:11:22")]),
        reg,
    )
    por_gps = validate_location(
        LocationEvidence(gps=GpsReading(latitude=lat, longitude=lon, accuracy_m=10)), reg
    )

    assert por_beacon.confidence > por_wifi.confidence > por_gps.confidence


# --------------------------------------------------------------------------
# Beacon — fronteiras
# --------------------------------------------------------------------------


def test_beacon_exatamente_no_limiar_e_aceito_com_confianca_no_piso():
    """Na borda da area: aceito, mas um passo atras ja o tiraria dela."""
    site = make_site()
    reg = registry([site], [make_beacon(site, min_rssi=-75)])

    veredito = validate_location(LocationEvidence(beacons=[beacon_reading(rssi=-75)]), reg)

    assert veredito.accepted
    assert veredito.confidence == 0.75


def test_beacon_um_db_abaixo_do_limiar_nao_confirma():
    site = make_site()
    reg = registry([site], [make_beacon(site, min_rssi=-75)])

    veredito = validate_location(LocationEvidence(beacons=[beacon_reading(rssi=-76)]), reg)

    assert veredito.method is LocationMethod.NONE
    assert not veredito.accepted


def test_beacon_fraco_explica_o_motivo():
    """O funcionario precisa saber por que nao passou, nao so que nao passou."""
    site = make_site()
    reg = registry([site], [make_beacon(site, label="Portao A", min_rssi=-75)])

    veredito = validate_location(LocationEvidence(beacons=[beacon_reading(rssi=-88)]), reg)

    assert any("Portao A" in nota and "-88" in nota for nota in veredito.notes)


def test_sinal_forte_leva_a_confianca_ao_teto():
    site = make_site()
    reg = registry([site], [make_beacon(site, min_rssi=-80)])

    veredito = validate_location(LocationEvidence(beacons=[beacon_reading(rssi=-55)]), reg)

    assert veredito.confidence == 0.95


def test_entre_varios_beacons_vence_o_mais_proximo():
    """Areas vizinhas se sobrepoem; o sinal mais forte e o da area certa."""
    site = make_site()
    portao = make_beacon(site, label="Portao A", instance=INSTANCE_PORTAO)
    almox = make_beacon(site, label="Almoxarifado", instance=INSTANCE_ALMOXARIFADO)
    reg = registry([site], [portao, almox])

    veredito = validate_location(
        LocationEvidence(
            beacons=[
                beacon_reading(INSTANCE_PORTAO, rssi=-80),
                beacon_reading(INSTANCE_ALMOXARIFADO, rssi=-55),
            ]
        ),
        reg,
    )

    assert veredito.beacon_id == almox.id
    assert veredito.beacon_rssi == -55


def test_beacon_desconhecido_e_ignorado():
    """Beacon de outra empresa, ou de um vizinho, nao confirma nada."""
    site = make_site()
    reg = registry([site], [make_beacon(site, instance=INSTANCE_PORTAO)])

    veredito = validate_location(
        LocationEvidence(beacons=[beacon_reading("00000000ffff", rssi=-40)]), reg
    )

    assert veredito.method is LocationMethod.NONE


def test_beacon_desativado_deixa_de_valer():
    """Beacon removido do hangar e desativado no painel para de contar na hora."""
    site = make_site()
    reg = registry([site], [make_beacon(site, is_active=False)])

    veredito = validate_location(LocationEvidence(beacons=[beacon_reading(rssi=-40)]), reg)

    assert veredito.method is LocationMethod.NONE


# --------------------------------------------------------------------------
# Beacon identificado por MAC
# --------------------------------------------------------------------------


def test_beacon_por_mac_confirma_presenca():
    """Ultimo recurso, para hardware cujo anuncio nao sabemos interpretar.

    Tambem resolve o caso de varios beacons sairem de fabrica com o mesmo
    UUID/major/minor: o MAC e unico por aparelho.
    """
    site = make_site()
    reg = registry([site], [make_beacon_mac(site)])

    veredito = validate_location(
        LocationEvidence(
            beacons=[
                BeaconReading(
                    protocol=BeaconProtocol.MAC,
                    mac_address="7C:EC:79:44:C5:B5",
                    rssi=-56,
                )
            ]
        ),
        reg,
    )

    assert veredito.method is LocationMethod.BEACON
    assert veredito.accepted
    assert veredito.beacon_rssi == -56


def test_mac_com_grafia_diferente_ainda_casa():
    """A normalizacao vale igual para MAC: o scanner mostra em maiusculas."""
    site = make_site()
    reg = registry([site], [make_beacon_mac(site, mac="7c:ec:79:44:c5:b5")])

    for grafia in ("7C:EC:79:44:C5:B5", "7c-ec-79-44-c5-b5", "7CEC7944C5B5"):
        veredito = validate_location(
            LocationEvidence(
                beacons=[
                    BeaconReading(
                        protocol=BeaconProtocol.MAC, mac_address=grafia, rssi=-56
                    )
                ]
            ),
            reg,
        )
        assert veredito.accepted, grafia


def test_mac_desconhecido_e_ignorado():
    site = make_site()
    reg = registry([site], [make_beacon_mac(site, mac="7c:ec:79:44:c5:b5")])

    veredito = validate_location(
        LocationEvidence(
            beacons=[
                BeaconReading(
                    protocol=BeaconProtocol.MAC, mac_address="aa:bb:cc:dd:ee:ff", rssi=-40
                )
            ]
        ),
        reg,
    )

    assert veredito.method is LocationMethod.NONE


def test_mac_abaixo_do_limiar_nao_confirma():
    site = make_site()
    reg = registry([site], [make_beacon_mac(site, min_rssi=-70)])

    veredito = validate_location(
        LocationEvidence(
            beacons=[
                BeaconReading(
                    protocol=BeaconProtocol.MAC,
                    mac_address="7c:ec:79:44:c5:b5",
                    rssi=-85,
                )
            ]
        ),
        reg,
    )

    assert veredito.method is LocationMethod.NONE


def test_protocolos_diferentes_nao_se_confundem():
    """Um beacon cadastrado por MAC nao casa com uma leitura de iBeacon.

    A identidade inclui o protocolo, entao os espacos de identificador ficam
    separados — o que evita um casamento acidental entre formatos.
    """
    site = make_site()
    reg = registry([site], [make_beacon_mac(site, mac="7c:ec:79:44:c5:b5")])

    veredito = validate_location(
        LocationEvidence(
            beacons=[
                BeaconReading(
                    protocol=BeaconProtocol.IBEACON,
                    ibeacon_uuid="4152554e-f99b-4a3b-86d0-947070693a78",
                    ibeacon_major=0,
                    ibeacon_minor=0,
                    rssi=-50,
                )
            ]
        ),
        reg,
    )

    assert veredito.method is LocationMethod.NONE


def test_varios_beacons_de_protocolos_diferentes_no_mesmo_local():
    """Migracao gradual: o local pode ter beacons antigos e novos ao mesmo tempo."""
    site = make_site()
    reg = registry(
        [site],
        [make_beacon(site, label="Eddystone"), make_beacon_mac(site, label="Aruba")],
    )

    veredito = validate_location(
        LocationEvidence(
            beacons=[
                beacon_reading(rssi=-80),
                BeaconReading(
                    protocol=BeaconProtocol.MAC,
                    mac_address="7c:ec:79:44:c5:b5",
                    rssi=-55,
                ),
            ]
        ),
        reg,
    )

    # Vence o sinal mais forte, independentemente do protocolo.
    assert veredito.accepted
    assert veredito.beacon_rssi == -55


# --------------------------------------------------------------------------
# Wi-Fi — o que o BSSID protege
# --------------------------------------------------------------------------


def test_ssid_sozinho_vale_menos_que_bssid():
    """Qualquer celular cria um hotspot com o nome da empresa em dez segundos."""
    site = make_site()
    reg = registry([site], [], [make_wifi(site, bssid=None)])

    veredito = validate_location(
        LocationEvidence(wifi=[WifiReading(ssid="EmpresaDemo-Corp")]), reg
    )

    assert veredito.method is LocationMethod.WIFI
    assert veredito.confidence == 0.35
    assert any("apenas pelo nome" in nota for nota in veredito.notes)


def test_ssid_certo_em_ponto_de_acesso_desconhecido_nao_confirma():
    """O caso do hotspot falso: nome da empresa, hardware de outra pessoa."""
    site = make_site()
    reg = registry([site], [], [make_wifi(site, bssid="a4:2b:8c:00:11:22")])

    veredito = validate_location(
        LocationEvidence(
            wifi=[WifiReading(ssid="EmpresaDemo-Corp", bssid="de:ad:be:ef:00:01")]
        ),
        reg,
    )

    assert veredito.method is LocationMethod.NONE
    assert any("desconhecido" in nota for nota in veredito.notes)


def test_bssid_confirma_mesmo_com_ssid_diferente():
    """O AP e o mesmo hardware; o nome da rede pode ter sido renomeado."""
    site = make_site()
    reg = registry([site], [], [make_wifi(site, ssid="Nome-Antigo")])

    veredito = validate_location(
        LocationEvidence(wifi=[WifiReading(ssid="Nome-Novo", bssid="a4:2b:8c:00:11:22")]),
        reg,
    )

    assert veredito.method is LocationMethod.WIFI
    assert veredito.confidence == 0.70


def test_rede_desconhecida_nao_confirma():
    site = make_site()
    reg = registry([site], [], [make_wifi(site)])

    veredito = validate_location(
        LocationEvidence(wifi=[WifiReading(ssid="Vizinho-5G", bssid="11:22:33:44:55:66")]),
        reg,
    )

    assert veredito.method is LocationMethod.NONE


def test_bssid_encontrado_entre_varias_redes_visiveis():
    """O aparelho enxerga a vizinhanca inteira; basta uma ser a da empresa."""
    site = make_site()
    reg = registry([site], [], [make_wifi(site)])

    veredito = validate_location(
        LocationEvidence(
            wifi=[
                WifiReading(ssid="Vizinho-1", bssid="11:11:11:11:11:11"),
                WifiReading(ssid="Vizinho-2", bssid="22:22:22:22:22:22"),
                WifiReading(ssid="EmpresaDemo-Corp", bssid="a4:2b:8c:00:11:22"),
            ]
        ),
        reg,
    )

    assert veredito.method is LocationMethod.WIFI
    assert veredito.confidence == 0.70


# --------------------------------------------------------------------------
# GPS — fronteiras e imprecisao
# --------------------------------------------------------------------------


def test_gps_dentro_do_raio():
    site = make_site(radius=200)
    lat, lon = coord_a_metros(150)
    reg = registry([site])

    veredito = validate_location(
        LocationEvidence(gps=GpsReading(latitude=lat, longitude=lon, accuracy_m=10)), reg
    )

    assert veredito.accepted
    assert veredito.method is LocationMethod.GPS


def test_gps_fora_do_raio():
    site = make_site(radius=200)
    lat, lon = coord_a_metros(600)
    reg = registry([site])

    veredito = validate_location(
        LocationEvidence(gps=GpsReading(latitude=lat, longitude=lon, accuracy_m=10)), reg
    )

    assert veredito.method is LocationMethod.NONE
    assert any("fora do raio" in nota for nota in veredito.notes)


def test_imprecisao_beneficia_quem_esta_na_borda():
    """Ligeiramente fora, mas dentro da margem de erro: aceito.

    Beneficiar o caso comum e deliberado (decisao D5): quem esta de fato no
    local nao pode ser barrado por 30 m de erro de GPS. O ponto duvidoso vai
    para revisao, nao para recusa.
    """
    site = make_site(radius=200)
    lat, lon = coord_a_metros(230)
    reg = registry([site])

    veredito = validate_location(
        LocationEvidence(gps=GpsReading(latitude=lat, longitude=lon, accuracy_m=50)), reg
    )

    assert veredito.accepted


def test_imprecisao_grande_demais_nao_confirma_nem_no_centro():
    """Circulo de incerteza maior que o local nao distingue hangar de bairro."""
    site = make_site(radius=200)
    reg = registry([site])

    veredito = validate_location(
        LocationEvidence(
            gps=GpsReading(latitude=HANGAR_LAT, longitude=HANGAR_LON, accuracy_m=900)
        ),
        reg,
    )

    assert veredito.method is LocationMethod.NONE
    assert any("imprecisa demais" in nota for nota in veredito.notes)


def test_confianca_do_gps_cai_com_a_imprecisao():
    site = make_site(radius=200)
    reg = registry([site])

    preciso = validate_location(
        LocationEvidence(
            gps=GpsReading(latitude=HANGAR_LAT, longitude=HANGAR_LON, accuracy_m=5)
        ),
        reg,
    )
    impreciso = validate_location(
        LocationEvidence(
            gps=GpsReading(latitude=HANGAR_LAT, longitude=HANGAR_LON, accuracy_m=150)
        ),
        reg,
    )

    assert preciso.confidence > impreciso.confidence


def test_confianca_do_gps_cai_com_a_distancia():
    site = make_site(radius=200)
    reg = registry([site])

    centro = validate_location(
        LocationEvidence(
            gps=GpsReading(latitude=HANGAR_LAT, longitude=HANGAR_LON, accuracy_m=10)
        ),
        reg,
    )
    lat, lon = coord_a_metros(180)
    borda = validate_location(
        LocationEvidence(gps=GpsReading(latitude=lat, longitude=lon, accuracy_m=10)), reg
    )

    assert centro.confidence > borda.confidence


def test_gps_escolhe_o_local_mais_proximo():
    """Empresa com mais de uma unidade: vale a que o funcionario esta."""
    hangar = make_site(name="Hangar", radius=200)
    lat_escritorio, lon_escritorio = coord_a_metros(50_000)
    escritorio = make_site(
        name="Escritorio", latitude=lat_escritorio, longitude=lon_escritorio, radius=200
    )
    reg = registry([hangar, escritorio])

    lat, lon = coord_a_metros(50_020)
    veredito = validate_location(
        LocationEvidence(gps=GpsReading(latitude=lat, longitude=lon, accuracy_m=10)), reg
    )

    assert veredito.site_name == "Escritorio"


def test_site_sem_coordenadas_nao_participa_do_gps():
    site = make_site(latitude=None, longitude=None)
    reg = registry([site])

    veredito = validate_location(
        LocationEvidence(
            gps=GpsReading(latitude=HANGAR_LAT, longitude=HANGAR_LON, accuracy_m=10)
        ),
        reg,
    )

    assert veredito.method is LocationMethod.NONE
    assert any("coordenadas cadastradas" in nota for nota in veredito.notes)


def test_site_inativo_nao_participa_do_gps():
    site = make_site(is_active=False)
    reg = registry([site])

    veredito = validate_location(
        LocationEvidence(
            gps=GpsReading(latitude=HANGAR_LAT, longitude=HANGAR_LON, accuracy_m=10)
        ),
        reg,
    )

    assert veredito.method is LocationMethod.NONE


# --------------------------------------------------------------------------
# Sinais que se contradizem
# --------------------------------------------------------------------------


def test_beacon_do_hangar_visto_de_outra_cidade_e_sinalizado():
    """O cenario concreto: advertisement falso transmitido de casa.

    O beacon "confirma", mas o GPS aponta a 100 km. A contradicao e o que
    denuncia — nenhum dos sinais sozinho contaria essa historia.
    """
    site = make_site(radius=200)
    reg = registry([site], [make_beacon(site)])

    lat, lon = coord_a_metros(100_000)
    veredito = validate_location(
        LocationEvidence(
            beacons=[beacon_reading(rssi=-50)],
            gps=GpsReading(latitude=lat, longitude=lon, accuracy_m=20),
        ),
        reg,
    )

    assert veredito.method is LocationMethod.BEACON
    assert veredito.accepted
    assert veredito.inconsistencies
    assert veredito.needs_review
    assert "km dali" in veredito.inconsistencies[0]


def test_erro_de_gps_dentro_do_galpao_nao_e_tratado_como_fraude():
    """GPS em galpao metalico erra centenas de metros; isso nao e suspeito.

    A folga precisa ser generosa justamente porque o erro de multipercurso e a
    razao de os beacons existirem — trata-lo como fraude reprovaria gente
    honesta com o sinal mais confiavel de todos na mao.
    """
    site = make_site(radius=200)
    reg = registry([site], [make_beacon(site)])

    lat, lon = coord_a_metros(800)
    veredito = validate_location(
        LocationEvidence(
            beacons=[beacon_reading(rssi=-50)],
            gps=GpsReading(latitude=lat, longitude=lon, accuracy_m=100),
        ),
        reg,
    )

    assert veredito.accepted
    assert not veredito.inconsistencies
    assert not veredito.needs_review


def test_sem_gps_nao_ha_como_detectar_incoerencia():
    site = make_site()
    reg = registry([site], [make_beacon(site)])

    veredito = validate_location(LocationEvidence(beacons=[beacon_reading()]), reg)

    assert veredito.inconsistencies == ()


def test_wifi_tambem_e_cruzado_com_o_gps():
    site = make_site(radius=200)
    reg = registry([site], [], [make_wifi(site)])

    lat, lon = coord_a_metros(100_000)
    veredito = validate_location(
        LocationEvidence(
            wifi=[WifiReading(ssid="EmpresaDemo-Corp", bssid="a4:2b:8c:00:11:22")],
            gps=GpsReading(latitude=lat, longitude=lon, accuracy_m=20),
        ),
        reg,
    )

    assert veredito.method is LocationMethod.WIFI
    assert veredito.inconsistencies


# --------------------------------------------------------------------------
# Payload de auditoria
# --------------------------------------------------------------------------


def test_auditoria_guarda_ate_as_leituras_descartadas():
    """Reavaliar um ponto contestado exige o que foi descartado, nao so o que venceu."""
    site = make_site()
    reg = registry([site], [make_beacon(site, min_rssi=-70)])

    evidencia = LocationEvidence(
        beacons=[
            beacon_reading(INSTANCE_PORTAO, rssi=-50),
            beacon_reading("00000000ffff", rssi=-90),
        ],
        wifi=[WifiReading(ssid="Vizinho", bssid="11:22:33:44:55:66")],
        gps=GpsReading(latitude=HANGAR_LAT, longitude=HANGAR_LON, accuracy_m=12),
    )
    veredito = validate_location(evidencia, reg)
    payload = build_audit_payload(evidencia, veredito)

    assert len(payload["observado"]["beacons"]) == 2
    assert len(payload["observado"]["wifi"]) == 1
    assert payload["observado"]["gps"]["accuracy_m"] == 12
    assert payload["conclusao"]["method"] == "beacon"
    assert payload["conclusao"]["accepted"] is True


def test_auditoria_registra_a_conclusao_que_valia_na_epoca():
    """A regra muda (limiar recalibrado, beacon movido); a conclusao gravada nao."""
    site = make_site()
    reg = registry([site])

    evidencia = LocationEvidence()
    payload = build_audit_payload(evidencia, validate_location(evidencia, reg))

    assert payload["conclusao"]["method"] == "none"
    assert payload["conclusao"]["accepted"] is False
    assert payload["conclusao"]["reason"]


def test_payload_e_serializavel_em_json():
    """Vai para uma coluna jsonb; um UUID solto quebraria a gravacao."""
    import json

    site = make_site()
    reg = registry([site], [make_beacon(site)])
    evidencia = LocationEvidence(beacons=[beacon_reading()])

    payload = build_audit_payload(evidencia, validate_location(evidencia, reg))

    assert json.loads(json.dumps(payload)) == payload


# --------------------------------------------------------------------------
# Distancia
# --------------------------------------------------------------------------


def test_haversine_mesma_coordenada_da_zero():
    assert haversine_distance_m(HANGAR_LAT, HANGAR_LON, HANGAR_LAT, HANGAR_LON) == 0.0


def test_haversine_confere_com_a_distancia_esperada():
    lat, lon = coord_a_metros(1000)
    assert haversine_distance_m(HANGAR_LAT, HANGAR_LON, lat, lon) == pytest.approx(
        1000, abs=5
    )


def test_haversine_e_simetrica():
    lat, lon = coord_a_metros(500)
    ida = haversine_distance_m(HANGAR_LAT, HANGAR_LON, lat, lon)
    volta = haversine_distance_m(lat, lon, HANGAR_LAT, HANGAR_LON)
    assert ida == pytest.approx(volta)


def test_haversine_atravessa_o_antimeridiano():
    """Longitude 179.9 e -179.9 sao vizinhas, nao estao a meio mundo."""
    distancia = haversine_distance_m(0.0, 179.95, 0.0, -179.95)
    assert distancia == pytest.approx(11_130, rel=0.01)
