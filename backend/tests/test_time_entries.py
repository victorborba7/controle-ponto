"""Bater ponto, ponta a ponta.

Exercita a orquestracao inteira contra a API: aparelho pareado, selfie,
reconhecimento facial contra os templates cadastrados, cadeia de localizacao e
gravacao. Usa a engine stub, em que a cor da imagem e a identidade — assim
"o rosto de outra pessoa" vira um cenario explicito no teste.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, TimeEntry
from app.models.enums import EntryType, LocationMethod, TimeEntryStatus
from tests.conftest import (
    HANGAR_LAT,
    HANGAR_LON,
    INSTANCE,
    NAMESPACE,
    OUTRA_PESSOA,
    SEM_SINAL,
    TEST_PASSWORD,
    auth_header,
    bater_ponto,
    com_beacon,
    com_gps,
    com_wifi,
    create_admin,
    create_employee,
    create_tenant,
    device_payload,
    login_admin,
)

# --------------------------------------------------------------------------
# O criterio de pronto: os quatro metodos de localizacao
# --------------------------------------------------------------------------


async def test_ponto_por_beacon(client: AsyncClient, cenario: dict):
    response = await bater_ponto(client, cenario, evidence=com_beacon())

    assert response.status_code == 201, response.text
    entry = response.json()["entry"]
    assert entry["location_method"] == "beacon"
    assert entry["status"] == "approved"
    assert entry["beacon_rssi"] == -55
    assert entry["location_confidence"] >= 0.75
    assert response.json()["message"] == "Ponto registrado."


async def test_ponto_por_wifi(client: AsyncClient, cenario: dict):
    response = await bater_ponto(client, cenario, evidence=com_wifi())

    entry = response.json()["entry"]
    assert entry["location_method"] == "wifi"
    assert entry["status"] == "approved"
    assert entry["location_confidence"] == 0.70


async def test_ponto_por_gps(client: AsyncClient, cenario: dict):
    response = await bater_ponto(client, cenario, evidence=com_gps())

    entry = response.json()["entry"]
    assert entry["location_method"] == "gps"
    assert entry["status"] == "approved"
    assert entry["distance_to_site_m"] == pytest.approx(50, abs=3)


async def test_ponto_sem_sinal_nenhum_vai_para_revisao(client: AsyncClient, cenario: dict):
    """Registra e sinaliza (D5): barrar quem esta no local e pior."""
    response = await bater_ponto(client, cenario, evidence=SEM_SINAL)

    assert response.status_code == 201
    entry = response.json()["entry"]
    assert entry["location_method"] == "none"
    assert entry["status"] == "pending_review"
    assert "conferencia" in response.json()["message"]


# --------------------------------------------------------------------------
# Reconhecimento facial
# --------------------------------------------------------------------------


async def test_rosto_de_outra_pessoa_nao_registra_ponto(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    response = await bater_ponto(client, cenario, cor=OUTRA_PESSOA)

    assert response.status_code == 422
    assert "Nao reconhecemos seu rosto" in response.json()["detail"]
    assert (await db.execute(select(TimeEntry))).scalars().all() == []


async def test_tentativa_recusada_fica_na_auditoria(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    """Sem registro de ponto, mas com rastro: e o que permite investigar depois."""
    await bater_ponto(client, cenario, cor=OUTRA_PESSOA)

    registros = (await db.execute(select(AuditLog))).scalars().all()
    recusas = [r for r in registros if r.payload and r.payload.get("recusado")]

    assert len(recusas) == 1
    assert recusas[0].payload["face_score"] < 0.32


async def test_selfie_de_tentativa_recusada_nao_e_guardada(
    client: AsyncClient, cenario: dict, storage_dir
):
    """A foto e de quem o sistema concluiu NAO ser o titular.

    Guardar biometria de um terceiro que nunca consentiu criaria exatamente o
    problema que a LGPD existe para evitar.
    """
    await bater_ponto(client, cenario, cor=OUTRA_PESSOA)

    selfies = storage_dir / "selfies"
    assert not selfies.exists() or list(selfies.iterdir()) == []


async def test_selfie_aprovada_e_guardada_cifrada(
    client: AsyncClient, db: AsyncSession, cenario: dict, storage_dir
):
    await bater_ponto(client, cenario)

    entry = await db.scalar(select(TimeEntry))
    assert entry.selfie_image_key.startswith("selfies/")

    bruto = (storage_dir / entry.selfie_image_key).read_bytes()
    assert not bruto.startswith(b"\x89PNG")


async def test_funcionario_sem_cadastro_biometrico(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    await create_employee(db, cenario["tenant"], external_code="0002", name="Sem Rosto")
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

    response = await bater_ponto(
        client, cenario, headers=auth_header(login.json()["tokens"])
    )

    assert response.status_code == 412
    assert "Procure o RH" in response.json()["detail"]


async def test_foto_sem_rosto_e_recusada(client: AsyncClient, cenario: dict):
    response = await bater_ponto(client, cenario, cor=(0, 0, 0))

    assert response.status_code == 422
    assert "rosto" in response.json()["detail"].lower()


# --------------------------------------------------------------------------
# Idempotencia e intervalo minimo
# --------------------------------------------------------------------------


async def test_reenvio_com_a_mesma_chave_nao_duplica(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    """O cenario real: area sem sinal, o app reenvia sem saber se chegou."""
    chave = f"batida-{uuid.uuid4()}"

    primeira = await bater_ponto(client, cenario, idempotency_key=chave)
    segunda = await bater_ponto(client, cenario, idempotency_key=chave)

    assert primeira.status_code == 201
    assert segunda.status_code == 201
    assert primeira.json()["entry"]["id"] == segunda.json()["entry"]["id"]
    assert segunda.json()["duplicate"] is True
    assert "ja havia sido registrado" in segunda.json()["message"]

    assert len((await db.execute(select(TimeEntry))).scalars().all()) == 1


async def test_duas_batidas_coladas_sao_o_mesmo_toque(
    client: AsyncClient, cenario: dict
):
    await bater_ponto(client, cenario)
    segunda = await bater_ponto(client, cenario)

    assert segunda.status_code == 409
    assert "acabou de bater" in segunda.json()["detail"]


async def test_batida_apos_o_intervalo_minimo_e_aceita(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    await bater_ponto(client, cenario)

    entry = await db.scalar(select(TimeEntry))
    entry.recorded_at = datetime.now(UTC) - timedelta(hours=8)
    await db.commit()

    segunda = await bater_ponto(client, cenario)
    assert segunda.status_code == 201


# --------------------------------------------------------------------------
# Entrada e saida
# --------------------------------------------------------------------------


async def test_primeira_batida_do_dia_e_entrada(client: AsyncClient, cenario: dict):
    response = await bater_ponto(client, cenario)
    assert response.json()["entry"]["entry_type"] == "in"


async def test_batida_seguinte_alterna_para_saida(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    """Deduzir tira do funcionario uma escolha que ele pode errar."""
    await bater_ponto(client, cenario)

    entry = await db.scalar(select(TimeEntry))
    entry.recorded_at = datetime.now(UTC) - timedelta(hours=8)
    await db.commit()

    saida = await bater_ponto(client, cenario)
    assert saida.json()["entry"]["entry_type"] == "out"


async def test_tipo_informado_pelo_app_e_respeitado(client: AsyncClient, cenario: dict):
    response = await bater_ponto(client, cenario, entry_type="out")
    assert response.json()["entry"]["entry_type"] == "out"


# --------------------------------------------------------------------------
# Aparelho
# --------------------------------------------------------------------------


async def test_aparelho_revogado_nao_bate_ponto(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    from app.models import Device

    device = await db.scalar(
        select(Device).where(Device.id == uuid.UUID(cenario["device_id"]))
    )
    device.revoked_at = datetime.now(UTC)
    await db.commit()

    response = await bater_ponto(client, cenario)

    assert response.status_code == 403
    assert "desvinculado" in response.json()["detail"]


async def test_admin_nao_bate_ponto_por_ninguem(client: AsyncClient, cenario: dict):
    """Bater ponto e ato pessoal."""
    response = await bater_ponto(client, cenario, headers=cenario["admin"])
    assert response.status_code == 403


# --------------------------------------------------------------------------
# Divergencia de relogio
# --------------------------------------------------------------------------


async def test_envio_muito_atrasado_vai_para_revisao(client: AsyncClient, cenario: dict):
    """Batida represada numa area sem sinal e enviada horas depois."""
    response = await bater_ponto(
        client, cenario, client_recorded_at=datetime.now(UTC) - timedelta(hours=3)
    )

    entry = response.json()["entry"]
    assert entry["status"] == "pending_review"
    assert "atraso" in entry["decision_reason"]
    # O horario do servidor e o que vale; o do aparelho fica ao lado.
    assert entry["client_recorded_at"] is not None


# --------------------------------------------------------------------------
# Evidencia guardada
# --------------------------------------------------------------------------


async def test_payload_cru_da_localizacao_e_gravado(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    """Reavaliar um ponto contestado exige o que foi observado, nao so a conclusao."""
    evidencia = json.dumps(
        {
            "beacons": [
                {
                    "protocol": "eddystone",
                    "eddystone_namespace": NAMESPACE,
                    "eddystone_instance": INSTANCE,
                    "rssi": -55,
                },
                {
                    "protocol": "eddystone",
                    "eddystone_namespace": NAMESPACE,
                    "eddystone_instance": "00000000ffff",
                    "rssi": -90,
                },
            ],
            "wifi": [{"ssid": "Vizinho", "bssid": "11:22:33:44:55:66"}],
        }
    )
    await bater_ponto(client, cenario, evidence=evidencia)

    entry = await db.scalar(select(TimeEntry))

    assert len(entry.location_raw["observado"]["beacons"]) == 2
    assert len(entry.location_raw["observado"]["wifi"]) == 1
    assert entry.location_raw["conclusao"]["method"] == "beacon"


async def test_beacon_fraco_cai_para_gps(client: AsyncClient, cenario: dict):
    """A cadeia continua quando o elo mais forte nao confirma."""
    evidencia = json.dumps(
        {
            "beacons": [
                {
                    "protocol": "eddystone",
                    "eddystone_namespace": NAMESPACE,
                    "eddystone_instance": INSTANCE,
                    "rssi": -92,
                }
            ],
            "gps": {
                "latitude": HANGAR_LAT,
                "longitude": HANGAR_LON,
                "accuracy_m": 10,
            },
        }
    )
    response = await bater_ponto(client, cenario, evidence=evidencia)

    assert response.json()["entry"]["location_method"] == "gps"


async def test_incoerencia_entre_beacon_e_gps_vai_para_revisao(
    client: AsyncClient, cenario: dict
):
    """Beacon do hangar visto de outra cidade."""
    evidencia = json.dumps(
        {
            "beacons": [
                {
                    "protocol": "eddystone",
                    "eddystone_namespace": NAMESPACE,
                    "eddystone_instance": INSTANCE,
                    "rssi": -55,
                }
            ],
            "gps": {
                "latitude": HANGAR_LAT + 100_000 / 111_320.0,
                "longitude": HANGAR_LON,
                "accuracy_m": 20,
            },
        }
    )
    response = await bater_ponto(client, cenario, evidence=evidencia)

    entry = response.json()["entry"]
    assert entry["location_method"] == "beacon"
    assert entry["status"] == "pending_review"
    assert "km dali" in entry["decision_reason"]


# --------------------------------------------------------------------------
# Consulta
# --------------------------------------------------------------------------


async def test_rh_lista_com_nome_do_funcionario(client: AsyncClient, cenario: dict):
    await bater_ponto(client, cenario)

    listagem = await client.get("/api/v1/time-entries", headers=cenario["admin"])

    assert listagem.status_code == 200
    item = listagem.json()["items"][0]
    assert item["employee_name"] == "Joao"
    assert item["employee_code"] == "0001"
    assert item["site_name"] == "Hangar"
    assert item["location_method"] == "beacon"


async def test_filtro_por_metodo_de_localizacao(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    await bater_ponto(client, cenario, evidence=com_beacon())

    entry = await db.scalar(select(TimeEntry))
    entry.recorded_at = datetime.now(UTC) - timedelta(hours=8)
    await db.commit()

    await bater_ponto(client, cenario, evidence=com_gps())

    por_beacon = await client.get(
        "/api/v1/time-entries?location_method=beacon", headers=cenario["admin"]
    )
    por_gps = await client.get(
        "/api/v1/time-entries?location_method=gps", headers=cenario["admin"]
    )

    assert por_beacon.json()["total"] == 1
    assert por_gps.json()["total"] == 1


async def test_fila_de_revisao(client: AsyncClient, cenario: dict):
    await bater_ponto(client, cenario, evidence=SEM_SINAL)

    pendentes = await client.get(
        "/api/v1/time-entries?status=pending_review", headers=cenario["admin"]
    )
    assert pendentes.json()["total"] == 1


async def test_funcionario_ve_o_proprio_historico(client: AsyncClient, cenario: dict):
    await bater_ponto(client, cenario)

    historico = await client.get("/api/v1/time-entries/me", headers=cenario["app"])

    assert historico.status_code == 200
    assert historico.json()["total"] == 1


async def test_funcionario_nao_ve_o_ponto_dos_colegas(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    """Endpoint separado do RH justamente para nao haver caminho ate ali."""
    await bater_ponto(client, cenario)

    await create_employee(db, cenario["tenant"], external_code="0003")
    await db.commit()

    login = await client.post(
        "/api/v1/auth/employee/login",
        json={
            "tenant_slug": "acme",
            "external_code": "0003",
            "password": TEST_PASSWORD,
            "device": device_payload(),
        },
    )
    headers = auth_header(login.json()["tokens"])

    proprio = await client.get("/api/v1/time-entries/me", headers=headers)
    do_rh = await client.get("/api/v1/time-entries", headers=headers)

    assert proprio.json()["total"] == 0
    assert do_rh.status_code == 403


# --------------------------------------------------------------------------
# Revisao pelo RH
# --------------------------------------------------------------------------


async def test_rh_aprova_pendencia(client: AsyncClient, cenario: dict):
    pendente = await bater_ponto(client, cenario, evidence=SEM_SINAL)
    entry_id = pendente.json()["entry"]["id"]

    revisao = await client.patch(
        f"/api/v1/time-entries/{entry_id}/review",
        headers=cenario["admin"],
        json={"approved": True, "note": "Confirmado com o supervisor"},
    )

    assert revisao.status_code == 200
    corpo = revisao.json()
    assert corpo["status"] == "approved"
    assert corpo["review_note"] == "Confirmado com o supervisor"
    assert corpo["reviewed_at"] is not None


async def test_rh_rejeita_pendencia(client: AsyncClient, cenario: dict):
    pendente = await bater_ponto(client, cenario, evidence=SEM_SINAL)
    entry_id = pendente.json()["entry"]["id"]

    revisao = await client.patch(
        f"/api/v1/time-entries/{entry_id}/review",
        headers=cenario["admin"],
        json={"approved": False, "note": "Funcionario estava de folga"},
    )

    assert revisao.json()["status"] == "rejected"


async def test_nao_revisa_o_que_ja_foi_decidido(client: AsyncClient, cenario: dict):
    aprovado = await bater_ponto(client, cenario)
    entry_id = aprovado.json()["entry"]["id"]

    revisao = await client.patch(
        f"/api/v1/time-entries/{entry_id}/review",
        headers=cenario["admin"],
        json={"approved": False},
    )

    assert revisao.status_code == 409


async def test_revisao_registra_quem_decidiu(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    """Aprovacao sem autor nao serve de defesa em discussao trabalhista."""
    pendente = await bater_ponto(client, cenario, evidence=SEM_SINAL)
    entry_id = pendente.json()["entry"]["id"]

    await client.patch(
        f"/api/v1/time-entries/{entry_id}/review",
        headers=cenario["admin"],
        json={"approved": True},
    )

    entry = await db.scalar(select(TimeEntry).where(TimeEntry.id == uuid.UUID(entry_id)))
    assert entry.reviewed_by_user_id is not None
    assert entry.reviewed_at is not None


# --------------------------------------------------------------------------
# O que o painel consome
# --------------------------------------------------------------------------


async def test_painel_busca_a_foto_do_registro(client: AsyncClient, cenario: dict):
    """Servida pela API, e nao por URL do storage: a imagem e dado biometrico."""
    ponto = await bater_ponto(client, cenario)
    entry_id = ponto.json()["entry"]["id"]

    foto = await client.get(
        f"/api/v1/time-entries/{entry_id}/selfie", headers=cenario["admin"]
    )

    assert foto.status_code == 200
    assert foto.headers["content-type"].startswith("image/")
    assert foto.content.startswith(b"\x89PNG")
    # Sem copia em disco do navegador.
    assert "no-store" in foto.headers["cache-control"]


async def test_foto_de_outra_empresa_nao_e_servida(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    ponto = await bater_ponto(client, cenario)
    entry_id = ponto.json()["entry"]["id"]

    outra = await create_tenant(db, slug="vizinha3")
    await create_admin(db, outra, email="rh@vizinha3.com")
    await db.commit()
    login = await login_admin(client, outra, "rh@vizinha3.com")

    foto = await client.get(
        f"/api/v1/time-entries/{entry_id}/selfie", headers=auth_header(login["tokens"])
    )
    assert foto.status_code == 404


async def test_funcionario_nao_busca_foto_de_ponto(client: AsyncClient, cenario: dict):
    ponto = await bater_ponto(client, cenario)
    entry_id = ponto.json()["entry"]["id"]

    foto = await client.get(
        f"/api/v1/time-entries/{entry_id}/selfie", headers=cenario["app"]
    )
    assert foto.status_code == 403


async def test_rh_corrige_o_horario_de_uma_batida_atrasada(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    """O caso que motiva a funcionalidade: batida represada em area sem sinal.

    Ela chega com o horario do envio; sem correcao, o espelho de ponto ficaria
    errado justamente onde o funcionario nao teve culpa.
    """
    batida_real = datetime.now(UTC) - timedelta(hours=3)
    pendente = await bater_ponto(client, cenario, client_recorded_at=batida_real)
    entry_id = pendente.json()["entry"]["id"]
    horario_do_envio = pendente.json()["entry"]["recorded_at"]

    revisao = await client.patch(
        f"/api/v1/time-entries/{entry_id}/review",
        headers=cenario["admin"],
        json={
            "approved": True,
            "note": "Sem sinal no hangar; horario ajustado",
            "corrected_recorded_at": batida_real.isoformat(),
        },
    )

    assert revisao.status_code == 200
    assert revisao.json()["recorded_at"] != horario_do_envio

    entry = await db.scalar(select(TimeEntry).where(TimeEntry.id == uuid.UUID(entry_id)))
    assert abs((entry.recorded_at - batida_real).total_seconds()) < 2


async def test_correcao_de_horario_fica_na_trilha(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    """Sem os dois valores, uma batida ajustada seria indistinguivel de uma original."""
    batida_real = datetime.now(UTC) - timedelta(hours=3)
    pendente = await bater_ponto(client, cenario, client_recorded_at=batida_real)
    entry_id = pendente.json()["entry"]["id"]

    await client.patch(
        f"/api/v1/time-entries/{entry_id}/review",
        headers=cenario["admin"],
        json={"approved": True, "corrected_recorded_at": batida_real.isoformat()},
    )

    registros = (await db.execute(select(AuditLog))).scalars().all()
    revisoes = [r for r in registros if r.payload and "horario_corrigido" in r.payload]

    assert len(revisoes) == 1
    correcao = revisoes[0].payload["horario_corrigido"]
    assert correcao["de"] != correcao["para"]


async def test_exportacao_csv(client: AsyncClient, db: AsyncSession, cenario: dict):
    await bater_ponto(client, cenario, evidence=com_beacon())

    entry = await db.scalar(select(TimeEntry))
    entry.recorded_at = datetime.now(UTC) - timedelta(hours=8)
    await db.commit()

    await bater_ponto(client, cenario, evidence=com_gps())

    csv_resposta = await client.get(
        "/api/v1/time-entries/export/csv", headers=cenario["admin"]
    )

    assert csv_resposta.status_code == 200
    assert "attachment" in csv_resposta.headers["content-disposition"]

    texto = csv_resposta.text
    linhas = [linha for linha in texto.splitlines() if linha.strip()]

    assert linhas[0].startswith("﻿") or texto.startswith("﻿")
    assert "Metodo de localizacao" in linhas[0]
    assert len(linhas) == 3  # cabecalho + duas batidas
    assert "Beacon" in texto
    assert "GPS" in texto
    assert "Joao" in texto


async def test_csv_usa_o_formato_que_o_excel_em_portugues_espera(
    client: AsyncClient, cenario: dict
):
    """Ponto decimal e virgula separadora fariam a planilha abrir numa coluna so."""
    await bater_ponto(client, cenario)

    texto = (
        await client.get("/api/v1/time-entries/export/csv", headers=cenario["admin"])
    ).text
    linha_de_dados = [linha for linha in texto.splitlines() if "Joao" in linha][0]

    assert ";" in linha_de_dados
    assert "0,95" in linha_de_dados  # confianca do beacon, com virgula decimal


async def test_csv_respeita_os_filtros(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    await bater_ponto(client, cenario, evidence=com_beacon())

    entry = await db.scalar(select(TimeEntry))
    entry.recorded_at = datetime.now(UTC) - timedelta(hours=8)
    await db.commit()

    await bater_ponto(client, cenario, evidence=SEM_SINAL)

    apenas_pendentes = await client.get(
        "/api/v1/time-entries/export/csv?status=pending_review",
        headers=cenario["admin"],
    )
    linhas = [linha for linha in apenas_pendentes.text.splitlines() if linha.strip()]

    assert len(linhas) == 2  # cabecalho + a pendente
    assert "Em revisao" in apenas_pendentes.text


async def test_csv_nao_mistura_empresas(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    await bater_ponto(client, cenario)

    outra = await create_tenant(db, slug="vizinha4")
    await create_admin(db, outra, email="rh@vizinha4.com")
    await db.commit()
    login = await login_admin(client, outra, "rh@vizinha4.com")

    csv_resposta = await client.get(
        "/api/v1/time-entries/export/csv", headers=auth_header(login["tokens"])
    )
    linhas = [linha for linha in csv_resposta.text.splitlines() if linha.strip()]

    assert len(linhas) == 1  # so o cabecalho


# --------------------------------------------------------------------------
# Isolamento entre empresas
# --------------------------------------------------------------------------


async def test_ponto_de_outra_empresa_responde_404(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    await bater_ponto(client, cenario)
    entry = await db.scalar(select(TimeEntry))

    outra = await create_tenant(db, slug="vizinha")
    await create_admin(db, outra, email="rh@vizinha.com")
    await db.commit()

    login = await login_admin(client, outra, "rh@vizinha.com")
    response = await client.get(
        f"/api/v1/time-entries/{entry.id}", headers=auth_header(login["tokens"])
    )

    assert response.status_code == 404


async def test_listagem_nao_mistura_empresas(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    await bater_ponto(client, cenario)

    outra = await create_tenant(db, slug="vizinha2")
    await create_admin(db, outra, email="rh@vizinha2.com")
    await db.commit()

    login = await login_admin(client, outra, "rh@vizinha2.com")
    listagem = await client.get(
        "/api/v1/time-entries", headers=auth_header(login["tokens"])
    )

    assert listagem.json()["total"] == 0


# --------------------------------------------------------------------------
# Auditoria
# --------------------------------------------------------------------------


async def test_cada_batida_gera_trilha(
    client: AsyncClient, db: AsyncSession, cenario: dict
):
    await bater_ponto(client, cenario)

    registros = (await db.execute(select(AuditLog))).scalars().all()
    pontos = [r for r in registros if r.entity_type == "time_entry"]

    assert len(pontos) == 1
    assert pontos[0].payload["metodo"] == LocationMethod.BEACON.value
    assert pontos[0].payload["status"] == TimeEntryStatus.APPROVED.value
    assert pontos[0].payload["tipo"] == EntryType.IN.value
