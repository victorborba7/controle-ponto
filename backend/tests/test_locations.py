"""Locais, beacons e redes Wi-Fi.

O tema central destes testes e a **normalizacao dos identificadores**. Um
beacon gravado com grafia diferente da que o aparelho reporta nunca casa, e a
falha e silenciosa: nada erra, o beacon so nunca e reconhecido. E o tipo de
defeito que so aparece com alguem parado no hangar sem conseguir bater ponto.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.identifiers import (
    IdentifierError,
    normalize_bssid,
    normalize_eddystone_instance,
    normalize_eddystone_namespace,
    normalize_ibeacon_uuid,
    validate_rssi,
    validate_timezone,
)
from tests.conftest import (
    TEST_PASSWORD,
    auth_header,
    create_admin,
    create_employee,
    create_tenant,
    device_payload,
    login_admin,
)

NAMESPACE = "edd1ebeac04e5defa017"
INSTANCE_A = "000000000001"
INSTANCE_B = "000000000002"


@pytest.fixture
async def empresa(client: AsyncClient, db: AsyncSession):
    tenant = await create_tenant(db, slug="acme")
    await create_admin(db, tenant, email="rh@acme.com")
    await db.commit()

    login = await login_admin(client, tenant, "rh@acme.com")
    return {"tenant": tenant, "headers": auth_header(login["tokens"])}


@pytest.fixture
async def site(client: AsyncClient, empresa: dict) -> dict:
    response = await client.post(
        "/api/v1/sites",
        headers=empresa["headers"],
        json={
            "name": "Hangar Principal",
            "address": "Av. Monteiro Lobato, 1000",
            "latitude": -23.4356,
            "longitude": -46.4731,
            "geofence_radius_m": 200,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------
# Normalizacao — a unidade que sustenta tudo
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "entrada",
    [
        "edd1ebeac04e5defa017",
        "EDD1EBEAC04E5DEFA017",
        "ed-d1-eb-ea-c0-4e-5d-ef-a0-17",
        "ED D1 EB EA C0 4E 5D EF A0 17",
    ],
)
def test_namespace_converge_para_a_mesma_forma(entrada: str):
    """A etiqueta do fabricante vem em varias grafias; todas viram uma so."""
    assert normalize_eddystone_namespace(entrada) == NAMESPACE


def test_namespace_com_tamanho_errado():
    with pytest.raises(IdentifierError, match="10 bytes"):
        normalize_eddystone_namespace("abcd")


def test_instance_tem_6_bytes():
    assert normalize_eddystone_instance("00-00-00-00-00-01") == INSTANCE_A
    with pytest.raises(IdentifierError, match="6 bytes"):
        normalize_eddystone_instance(NAMESPACE)


@pytest.mark.parametrize(
    "entrada",
    [
        "aa:bb:cc:dd:ee:ff",
        "AA:BB:CC:DD:EE:FF",
        "aa-bb-cc-dd-ee-ff",
        "aabbccddeeff",
    ],
)
def test_bssid_converge_para_a_mesma_forma(entrada: str):
    assert normalize_bssid(entrada) == "aa:bb:cc:dd:ee:ff"


def test_bssid_invalido():
    with pytest.raises(IdentifierError, match="6 bytes"):
        normalize_bssid("aa:bb:cc")


def test_uuid_de_ibeacon_fica_canonico():
    assert (
        normalize_ibeacon_uuid("F7826DA6-4FA2-4E98-8024-BC5B71E0893E")
        == "f7826da6-4fa2-4e98-8024-bc5b71e0893e"
    )
    assert (
        normalize_ibeacon_uuid("f7826da64fa24e988024bc5b71e0893e")
        == "f7826da6-4fa2-4e98-8024-bc5b71e0893e"
    )


def test_uuid_invalido():
    with pytest.raises(IdentifierError, match="invalido"):
        normalize_ibeacon_uuid("nao-e-um-uuid")


@pytest.mark.parametrize("valor", [-60, -80, -100, -30])
def test_rssi_valido(valor: int):
    assert validate_rssi(valor) == valor


@pytest.mark.parametrize("valor", [0, 10, -120, -20])
def test_rssi_fora_da_faixa(valor: int):
    """RSSI positivo nao existe em medicao real; e erro de digitacao."""
    with pytest.raises(IdentifierError, match="RSSI"):
        validate_rssi(valor)


def test_fuso_valido_e_invalido():
    assert validate_timezone("America/Sao_Paulo") == "America/Sao_Paulo"
    with pytest.raises(IdentifierError, match="Fuso"):
        validate_timezone("America/Hangar")


# --------------------------------------------------------------------------
# Sites
# --------------------------------------------------------------------------


async def test_cadastrar_local(site: dict):
    assert site["name"] == "Hangar Principal"
    assert site["geofence_radius_m"] == 200
    assert site["timezone"] == "America/Sao_Paulo"
    assert site["beacon_count"] == 0


async def test_nome_de_local_duplicado(client: AsyncClient, empresa: dict, site: dict):
    repetido = await client.post(
        "/api/v1/sites", headers=empresa["headers"], json={"name": "Hangar Principal"}
    )
    assert repetido.status_code == 409


async def test_latitude_sem_longitude_e_recusada(client: AsyncClient, empresa: dict):
    response = await client.post(
        "/api/v1/sites",
        headers=empresa["headers"],
        json={"name": "Meio Local", "latitude": -23.4},
    )
    assert response.status_code == 422


async def test_atualizacao_nao_pode_deixar_coordenada_pela_metade(
    client: AsyncClient, empresa: dict, site: dict
):
    """Checado tambem no servico: um PATCH parcial contorna o schema de criacao."""
    response = await client.patch(
        f"/api/v1/sites/{site['id']}", headers=empresa["headers"], json={"latitude": None}
    )
    assert response.status_code == 422


async def test_raio_de_geofence_fora_da_faixa(client: AsyncClient, empresa: dict):
    """Abaixo de 10 m rejeita quem esta no local; acima de 5 km nao prova nada."""
    muito_pequeno = await client.post(
        "/api/v1/sites",
        headers=empresa["headers"],
        json={"name": "Minusculo", "geofence_radius_m": 5},
    )
    muito_grande = await client.post(
        "/api/v1/sites",
        headers=empresa["headers"],
        json={"name": "Enorme", "geofence_radius_m": 50000},
    )
    assert muito_pequeno.status_code == 422
    assert muito_grande.status_code == 422


async def test_fuso_invalido_e_recusado(client: AsyncClient, empresa: dict):
    response = await client.post(
        "/api/v1/sites",
        headers=empresa["headers"],
        json={"name": "Local", "timezone": "Brasil/Hangar"},
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------
# Beacons
# --------------------------------------------------------------------------


async def _criar_beacon(client, empresa, site, **overrides) -> dict:
    corpo = {
        "label": "Hangar - Portao A",
        "protocol": "eddystone",
        "eddystone_namespace": NAMESPACE,
        "eddystone_instance": INSTANCE_A,
        "min_rssi": -75,
    }
    corpo.update(overrides)
    return await client.post(
        f"/api/v1/sites/{site['id']}/beacons", headers=empresa["headers"], json=corpo
    )


async def test_cadastrar_beacon_eddystone(client: AsyncClient, empresa: dict, site: dict):
    response = await _criar_beacon(client, empresa, site)

    assert response.status_code == 201, response.text
    beacon = response.json()
    assert beacon["protocol"] == "eddystone"
    assert beacon["eddystone_namespace"] == NAMESPACE
    assert beacon["min_rssi"] == -75


async def test_identificador_e_normalizado_no_cadastro(
    client: AsyncClient, empresa: dict, site: dict
):
    """Digitado com hifens e em maiusculas, gravado na forma canonica."""
    response = await _criar_beacon(
        client,
        empresa,
        site,
        eddystone_namespace="ED-D1-EB-EA-C0-4E-5D-EF-A0-17",
        eddystone_instance="00:00:00:00:00:01",
    )

    beacon = response.json()
    assert beacon["eddystone_namespace"] == NAMESPACE
    assert beacon["eddystone_instance"] == INSTANCE_A


async def test_beacon_duplicado_e_recusado(client: AsyncClient, empresa: dict, site: dict):
    """O caso que o indice parcial passou a cobrir.

    A restricao anterior nao pegava isto: cobria tambem as colunas de iBeacon,
    que ficam nulas num beacon Eddystone, e no Postgres NULL e distinto de
    NULL — as duas linhas passavam como diferentes.
    """
    await _criar_beacon(client, empresa, site)
    repetido = await _criar_beacon(client, empresa, site, label="Outro nome, mesmo hardware")

    assert repetido.status_code == 409
    assert "ja esta cadastrado" in repetido.json()["detail"]


async def test_duplicidade_detectada_apesar_da_grafia_diferente(
    client: AsyncClient, empresa: dict, site: dict
):
    """Normalizar na entrada e o que faz a checagem de duplicidade funcionar."""
    await _criar_beacon(client, empresa, site)
    repetido = await _criar_beacon(
        client,
        empresa,
        site,
        label="Digitado diferente",
        eddystone_namespace="EDD1EBEAC04E5DEFA017",
        eddystone_instance="00-00-00-00-00-01",
    )
    assert repetido.status_code == 409


async def test_eddystone_sem_identificador(client: AsyncClient, empresa: dict, site: dict):
    response = await client.post(
        f"/api/v1/sites/{site['id']}/beacons",
        headers=empresa["headers"],
        json={"label": "Incompleto", "protocol": "eddystone"},
    )
    assert response.status_code == 422


async def test_eddystone_com_campos_de_ibeacon(
    client: AsyncClient, empresa: dict, site: dict
):
    """Protocolo trocado no painel geraria registro pela metade."""
    response = await _criar_beacon(
        client,
        empresa,
        site,
        ibeacon_uuid="f7826da6-4fa2-4e98-8024-bc5b71e0893e",
    )
    assert response.status_code == 422
    assert "nao deve receber campos de iBeacon" in str(response.json())


async def test_cadastrar_beacon_ibeacon(client: AsyncClient, empresa: dict, site: dict):
    """iBeacon segue suportado, mesmo com o Eddystone sendo o formato escolhido."""
    response = await client.post(
        f"/api/v1/sites/{site['id']}/beacons",
        headers=empresa["headers"],
        json={
            "label": "Legado",
            "protocol": "ibeacon",
            "ibeacon_uuid": "F7826DA6-4FA2-4E98-8024-BC5B71E0893E",
            "ibeacon_major": 1,
            "ibeacon_minor": 2,
        },
    )

    assert response.status_code == 201
    assert response.json()["ibeacon_uuid"] == "f7826da6-4fa2-4e98-8024-bc5b71e0893e"


async def test_ibeacon_sem_major_e_recusado(client: AsyncClient, empresa: dict, site: dict):
    response = await client.post(
        f"/api/v1/sites/{site['id']}/beacons",
        headers=empresa["headers"],
        json={
            "label": "Incompleto",
            "protocol": "ibeacon",
            "ibeacon_uuid": "f7826da6-4fa2-4e98-8024-bc5b71e0893e",
        },
    )
    assert response.status_code == 422


async def test_rssi_positivo_e_recusado(client: AsyncClient, empresa: dict, site: dict):
    response = await _criar_beacon(client, empresa, site, min_rssi=10)
    assert response.status_code == 422


async def test_desativar_beacon(client: AsyncClient, empresa: dict, site: dict):
    criado = await _criar_beacon(client, empresa, site)
    beacon_id = criado.json()["id"]

    response = await client.patch(
        f"/api/v1/sites/{site['id']}/beacons/{beacon_id}",
        headers=empresa["headers"],
        json={"is_active": False},
    )
    assert response.json()["is_active"] is False


# --------------------------------------------------------------------------
# Redes Wi-Fi
# --------------------------------------------------------------------------


async def test_cadastrar_rede_wifi(client: AsyncClient, empresa: dict, site: dict):
    response = await client.post(
        f"/api/v1/sites/{site['id']}/wifi-networks",
        headers=empresa["headers"],
        json={"ssid": "EmpresaDemo-Corp", "bssid": "A4:2B:8C:00:11:22", "label": "AP do hangar"},
    )

    assert response.status_code == 201
    assert response.json()["bssid"] == "a4:2b:8c:00:11:22"


async def test_bssid_duplicado(client: AsyncClient, empresa: dict, site: dict):
    corpo = {"ssid": "Rede", "bssid": "a4:2b:8c:00:11:22"}
    await client.post(
        f"/api/v1/sites/{site['id']}/wifi-networks", headers=empresa["headers"], json=corpo
    )
    repetido = await client.post(
        f"/api/v1/sites/{site['id']}/wifi-networks",
        headers=empresa["headers"],
        json={**corpo, "ssid": "Outro nome"},
    )
    assert repetido.status_code == 409


async def test_rede_sem_bssid_e_permitida(client: AsyncClient, empresa: dict, site: dict):
    """BSSID e opcional; a Etapa 6 e que dara menos confianca a um match so por SSID."""
    response = await client.post(
        f"/api/v1/sites/{site['id']}/wifi-networks",
        headers=empresa["headers"],
        json={"ssid": "Rede-Sem-BSSID"},
    )
    assert response.status_code == 201
    assert response.json()["bssid"] is None


# --------------------------------------------------------------------------
# location-config: o criterio de pronto da etapa
# --------------------------------------------------------------------------


@pytest.fixture
async def site_completo(client: AsyncClient, empresa: dict, site: dict) -> dict:
    """Um local com 2 beacons e 1 rede, como pede o criterio de pronto."""
    await _criar_beacon(client, empresa, site, label="Portao A", eddystone_instance=INSTANCE_A)
    await _criar_beacon(
        client, empresa, site, label="Almoxarifado", eddystone_instance=INSTANCE_B
    )
    await client.post(
        f"/api/v1/sites/{site['id']}/wifi-networks",
        headers=empresa["headers"],
        json={"ssid": "EmpresaDemo-Corp", "bssid": "a4:2b:8c:00:11:22"},
    )
    return site


async def test_location_config_traz_tudo(
    client: AsyncClient, empresa: dict, site_completo: dict
):
    response = await client.get(
        f"/api/v1/sites/{site_completo['id']}/location-config", headers=empresa["headers"]
    )

    assert response.status_code == 200
    config = response.json()

    assert config["site_name"] == "Hangar Principal"
    assert config["geofence_radius_m"] == 200
    assert len(config["beacons"]) == 2
    assert len(config["wifi_networks"]) == 1
    assert config["config_version"]

    instancias = {b["eddystone_instance"] for b in config["beacons"]}
    assert instancias == {INSTANCE_A, INSTANCE_B}


async def test_config_nao_expoe_o_nome_da_area(
    client: AsyncClient, empresa: dict, site_completo: dict
):
    """O rotulo interno diz respeito a planta da empresa e nao serve ao app."""
    response = await client.get(
        f"/api/v1/sites/{site_completo['id']}/location-config", headers=empresa["headers"]
    )
    assert "Almoxarifado" not in response.text


async def test_config_omite_o_que_esta_desativado(
    client: AsyncClient, empresa: dict, site_completo: dict
):
    """Beacon desativado no painel para de ser procurado no proximo cache."""
    beacons = await client.get(
        f"/api/v1/sites/{site_completo['id']}/beacons", headers=empresa["headers"]
    )
    alvo = beacons.json()["items"][0]["id"]

    await client.patch(
        f"/api/v1/sites/{site_completo['id']}/beacons/{alvo}",
        headers=empresa["headers"],
        json={"is_active": False},
    )

    config = await client.get(
        f"/api/v1/sites/{site_completo['id']}/location-config", headers=empresa["headers"]
    )
    assert len(config.json()["beacons"]) == 1


async def test_versao_da_config_muda_quando_algo_muda(
    client: AsyncClient, empresa: dict, site_completo: dict
):
    """Permite ao app perguntar 'mudou?' sem baixar tudo — util com conexao ruim."""
    url = f"/api/v1/sites/{site_completo['id']}/location-config"

    antes = (await client.get(url, headers=empresa["headers"])).json()["config_version"]

    await client.post(
        f"/api/v1/sites/{site_completo['id']}/wifi-networks",
        headers=empresa["headers"],
        json={"ssid": "Rede-Nova"},
    )

    depois = (await client.get(url, headers=empresa["headers"])).json()["config_version"]
    assert antes != depois


async def test_versao_e_estavel_sem_mudanca(
    client: AsyncClient, empresa: dict, site_completo: dict
):
    url = f"/api/v1/sites/{site_completo['id']}/location-config"
    primeira = (await client.get(url, headers=empresa["headers"])).json()["config_version"]
    segunda = (await client.get(url, headers=empresa["headers"])).json()["config_version"]
    assert primeira == segunda


async def test_app_do_funcionario_acessa_a_config(
    client: AsyncClient, db: AsyncSession, empresa: dict, site_completo: dict
):
    """O consumidor real deste endpoint e o app, nao o painel."""
    await create_employee(db, empresa["tenant"], external_code="0001")
    await db.commit()

    login = await client.post(
        "/api/v1/auth/employee/login",
        json={
            "tenant_slug": "acme",
            "external_code": "0001",
            "password": TEST_PASSWORD,
            "device": device_payload(),
        },
    )

    response = await client.get(
        f"/api/v1/sites/{site_completo['id']}/location-config",
        headers=auth_header(login.json()["tokens"]),
    )
    assert response.status_code == 200
    assert len(response.json()["beacons"]) == 2


async def test_funcionario_nao_cadastra_beacon(
    client: AsyncClient, db: AsyncSession, empresa: dict, site: dict
):
    await create_employee(db, empresa["tenant"], external_code="0002")
    await db.commit()

    login = await client.post(
        "/api/v1/auth/employee/login",
        json={
            "tenant_slug": "acme",
            "external_code": "0002",
            "password": TEST_PASSWORD,
            "device": device_payload(),
        },
    )

    response = await client.post(
        f"/api/v1/sites/{site['id']}/beacons",
        headers=auth_header(login.json()["tokens"]),
        json={
            "label": "Pirata",
            "protocol": "eddystone",
            "eddystone_namespace": NAMESPACE,
            "eddystone_instance": INSTANCE_A,
        },
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------
# Isolamento entre empresas
# --------------------------------------------------------------------------


async def test_local_de_outra_empresa_responde_404(
    client: AsyncClient, db: AsyncSession, empresa: dict
):
    outra = await create_tenant(db, slug="vizinha")
    await create_admin(db, outra, email="rh@vizinha.com")
    await db.commit()

    login_vizinha = await login_admin(client, outra, "rh@vizinha.com")
    site_alheio = await client.post(
        "/api/v1/sites",
        headers=auth_header(login_vizinha["tokens"]),
        json={"name": "Hangar da vizinha"},
    )

    response = await client.get(
        f"/api/v1/sites/{site_alheio.json()['id']}", headers=empresa["headers"]
    )
    assert response.status_code == 404


async def test_cadeia_de_validacao_funciona_com_dados_reais_do_banco(
    client: AsyncClient, db: AsyncSession, empresa: dict, site_completo: dict
):
    """Costura o cadastro real com a cadeia de validacao.

    Os testes da cadeia sao de mesa e montam o cadastro na mao. Este aqui cobre
    o unico trecho que eles nao alcancam: o carregador que traz do banco o que
    a cadeia recebe. Um erro ali (filtro de tenant faltando, campo mapeado
    errado) passaria despercebido pelos dois lados.
    """
    from app.db.repository import TenantRepository
    from app.models.enums import LocationMethod
    from app.schemas.evidence import BeaconReading, LocationEvidence
    from app.services.location import load_registry
    from app.services.location_validator import validate_location

    repo = TenantRepository(db, empresa["tenant"].id)
    registry = await load_registry(repo)

    assert len(registry.beacons) == 2
    assert len(registry.wifi_networks) == 1

    veredito = validate_location(
        LocationEvidence(
            beacons=[
                BeaconReading(
                    protocol="eddystone",
                    eddystone_namespace=NAMESPACE,
                    eddystone_instance=INSTANCE_A,
                    rssi=-60,
                )
            ]
        ),
        registry,
    )

    assert veredito.method is LocationMethod.BEACON
    assert veredito.accepted
    assert str(veredito.site_id) == site_completo["id"]


async def test_registro_de_outra_empresa_nao_entra_na_cadeia(
    client: AsyncClient, db: AsyncSession, empresa: dict, site_completo: dict
):
    """O beacon de um cliente nao pode confirmar presenca no local de outro."""
    from app.db.repository import TenantRepository
    from app.models.enums import LocationMethod
    from app.schemas.evidence import BeaconReading, LocationEvidence
    from app.services.location import load_registry
    from app.services.location_validator import validate_location

    outra = await create_tenant(db, slug="vizinha3")
    await db.commit()

    registry = await load_registry(TenantRepository(db, outra.id))

    veredito = validate_location(
        LocationEvidence(
            beacons=[
                BeaconReading(
                    protocol="eddystone",
                    eddystone_namespace=NAMESPACE,
                    eddystone_instance=INSTANCE_A,
                    rssi=-40,
                )
            ]
        ),
        registry,
    )

    assert veredito.method is LocationMethod.NONE


async def test_mesmo_beacon_em_empresas_diferentes_e_permitido(
    client: AsyncClient, db: AsyncSession, empresa: dict, site: dict
):
    """A unicidade e por empresa: dois clientes podem usar o mesmo lote de beacons."""
    await _criar_beacon(client, empresa, site)

    outra = await create_tenant(db, slug="vizinha2")
    await create_admin(db, outra, email="rh@vizinha2.com")
    await db.commit()

    login_vizinha = await login_admin(client, outra, "rh@vizinha2.com")
    headers_vizinha = auth_header(login_vizinha["tokens"])

    site_vizinha = await client.post(
        "/api/v1/sites", headers=headers_vizinha, json={"name": "Galpao"}
    )
    beacon = await client.post(
        f"/api/v1/sites/{site_vizinha.json()['id']}/beacons",
        headers=headers_vizinha,
        json={
            "label": "Mesmo hardware",
            "protocol": "eddystone",
            "eddystone_namespace": NAMESPACE,
            "eddystone_instance": INSTANCE_A,
        },
    )

    assert beacon.status_code == 201
