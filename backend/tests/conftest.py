"""Infraestrutura dos testes.

Roda contra um Postgres de verdade, num banco separado (`ponto_facial_test`),
e nao contra SQLite: o schema depende de pgvector e JSONB, entao um banco
substituto testaria algo diferente do que vai para producao.
"""

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.api.deps import get_engine, get_storage
from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_session
from app.facial.runner import AsyncFaceEngine
from app.facial.stub import StubFaceEngine, stub_image, stub_image_variant
from app.main import app
from app.models import Employee, Site, Tenant, User
from app.models.enums import UserRole
from app.services.storage import Storage, build_storage

TEST_DB_NAME = "ponto_facial_test"
TEST_PASSWORD = "senha-de-teste"

# 32 bytes em base64, so para teste.
TEST_ENCRYPTION_KEY = "ZGVzZW52b2x2aW1lbnRvLWFwZW5hcy1uYW8tdXNlISE="


def _swap_database(url: str, database: str) -> str:
    return f"{url.rsplit('/', 1)[0]}/{database}"


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Cria o banco de teste do zero uma vez por sessao de testes."""
    admin_engine = create_async_engine(
        _swap_database(settings.database_url_str, "postgres"),
        isolation_level="AUTOCOMMIT",
    )
    async with admin_engine.connect() as conn:
        # FORCE derruba conexoes penduradas de uma execucao anterior
        # interrompida, que senao impediriam o DROP.
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    await admin_engine.dispose()

    test_engine = create_async_engine(_swap_database(settings.database_url_str, TEST_DB_NAME))
    async with test_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    yield test_engine
    await test_engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Sessao do teste, com o banco limpo ao final.

    TRUNCATE em vez de recriar o schema a cada teste: mesma garantia de
    isolamento, ordens de grandeza mais rapido.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session

    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def storage_dir(tmp_path: Path) -> Path:
    """Diretorio de imagens do teste, descartado ao final."""
    return tmp_path / "storage"


@pytest.fixture
def storage(storage_dir: Path) -> Storage:
    """Storage do teste — cifrado, igual ao de producao, mas em tmp.

    Um teste que precise inspecionar os bytes crus usa `storage_dir` direto.
    """
    return build_storage(str(storage_dir), TEST_ENCRYPTION_KEY)


@pytest_asyncio.fixture(loop_scope="session")
async def client(db: AsyncSession, storage: Storage) -> AsyncGenerator[AsyncClient, None]:
    """Cliente HTTP falando com a app real.

    A app compartilha a sessao do teste, entao o que o teste grava fica
    visivel para o endpoint sem precisar de sincronizacao. O storage tambem e
    substituido, para nenhum teste escrever no diretorio real de imagens.
    """

    async def _override_session() -> AsyncGenerator[AsyncSession, None]:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_storage] = lambda: storage
    # Engine fixada na stub, independentemente de FACE_ENGINE no ambiente.
    # Estes testes montam cenarios com imagens sinteticas de cor solida, que o
    # ArcFace corretamente nao reconhece como rosto — sem esta fixacao, a suite
    # passaria ou falharia conforme qual compose estivesse rodando.
    # A engine real e verificada em test_facial_real_model.py, com foto de
    # rosto de verdade.
    app.dependency_overrides[get_engine] = lambda: AsyncFaceEngine(StubFaceEngine())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# Fabricas de dados
# --------------------------------------------------------------------------


async def create_tenant(
    db: AsyncSession,
    *,
    slug: str,
    name: str | None = None,
) -> Tenant:
    tenant = Tenant(name=name or f"Empresa {slug}", slug=slug)
    db.add(tenant)
    await db.flush()
    return tenant


async def create_admin(
    db: AsyncSession,
    tenant: Tenant,
    *,
    email: str = "admin@teste.com",
    role: UserRole = UserRole.OWNER,
    password: str = TEST_PASSWORD,
    is_active: bool = True,
) -> User:
    user = User(
        tenant_id=tenant.id,
        email=email,
        password_hash=hash_password(password),
        name="Admin de Teste",
        role=role,
        is_active=is_active,
    )
    db.add(user)
    await db.flush()
    return user


async def create_employee(
    db: AsyncSession,
    tenant: Tenant,
    *,
    external_code: str = "0001",
    name: str = "Funcionario de Teste",
    password: str | None = TEST_PASSWORD,
    **kwargs,
) -> Employee:
    employee = Employee(
        tenant_id=tenant.id,
        external_code=external_code,
        name=name,
        password_hash=hash_password(password) if password else None,
        **kwargs,
    )
    db.add(employee)
    await db.flush()
    return employee


async def create_site(db: AsyncSession, tenant: Tenant, *, name: str = "Hangar") -> Site:
    site = Site(
        tenant_id=tenant.id,
        name=name,
        latitude=-23.4356,
        longitude=-46.4731,
        geofence_radius_m=200,
    )
    db.add(site)
    await db.flush()
    return site


def device_payload(fingerprint: str | None = None) -> dict:
    return {
        "fingerprint": fingerprint or f"device-{uuid.uuid4().hex}",
        "platform": "android",
        "model": "Pixel 7",
        "os_version": "14",
        "app_version": "1.0.0",
    }


async def login_admin(
    client: AsyncClient,
    tenant: Tenant,
    email: str,
    password: str = TEST_PASSWORD,
) -> dict:
    """Faz login e devolve o corpo da resposta. Falha o teste se nao autenticar."""
    response = await client.post(
        "/api/v1/auth/admin/login",
        json={"tenant_slug": tenant.slug, "email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


def auth_header(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# --------------------------------------------------------------------------
# Cenario de batida de ponto
#
# Mora aqui, e nao no modulo de teste que o usa mais, porque ja e usado por
# mais de um. Importar fixture de um test_*.py para outro funciona no pytest,
# mas faz o nome ser redefinido em cada assinatura de teste — o que enche o
# lint de F811 e esconde uma redefinicao de verdade no meio do ruido.
# --------------------------------------------------------------------------

FUNCIONARIO = (200, 30, 30)
OUTRA_PESSOA = (30, 30, 200)

NAMESPACE = "edd1ebeac04e5defa017"
INSTANCE = "000000000001"
BSSID = "a4:2b:8c:00:11:22"

HANGAR_LAT, HANGAR_LON = -23.4356, -46.4731

SEM_SINAL = json.dumps({})


@pytest.fixture
async def cenario(client: AsyncClient, db: AsyncSession) -> dict:
    """Empresa, local, beacon, wifi e funcionario com rosto cadastrado."""
    tenant = await create_tenant(db, slug="acme")
    await create_admin(db, tenant, email="rh@acme.com")
    funcionario = await create_employee(db, tenant, external_code="0001", name="Joao")
    await db.commit()

    admin = auth_header((await login_admin(client, tenant, "rh@acme.com"))["tokens"])

    site = (
        await client.post(
            "/api/v1/sites",
            headers=admin,
            json={
                "name": "Hangar",
                "latitude": HANGAR_LAT,
                "longitude": HANGAR_LON,
                "geofence_radius_m": 200,
            },
        )
    ).json()

    await client.post(
        f"/api/v1/sites/{site['id']}/beacons",
        headers=admin,
        json={
            "label": "Portao A",
            "protocol": "eddystone",
            "eddystone_namespace": NAMESPACE,
            "eddystone_instance": INSTANCE,
            "min_rssi": -75,
        },
    )
    await client.post(
        f"/api/v1/sites/{site['id']}/wifi-networks",
        headers=admin,
        json={"ssid": "Acme-Corp", "bssid": BSSID},
    )

    enrollment = await client.post(
        f"/api/v1/employees/{funcionario.id}/face-templates",
        headers=admin,
        files=[
            ("images", ("f1.png", stub_image(FUNCIONARIO), "image/png")),
            ("images", ("f2.png", stub_image_variant(FUNCIONARIO, shift=4), "image/png")),
            ("images", ("f3.png", stub_image_variant(FUNCIONARIO, shift=8), "image/png")),
        ],
        data={"consent_policy_version": "2026.1", "consent_granted": "true"},
    )
    assert enrollment.status_code == 201, enrollment.text

    login = await client.post(
        "/api/v1/auth/employee/login",
        json={
            "tenant_slug": "acme",
            "external_code": "0001",
            "password": TEST_PASSWORD,
            "device": device_payload("celular-do-joao"),
        },
    )

    return {
        "tenant": tenant,
        "funcionario": funcionario,
        "site": site,
        "admin": admin,
        "app": auth_header(login.json()["tokens"]),
        "device_id": login.json()["device_id"],
    }


def com_beacon(rssi: int = -55) -> str:
    return json.dumps(
        {
            "beacons": [
                {
                    "protocol": "eddystone",
                    "eddystone_namespace": NAMESPACE,
                    "eddystone_instance": INSTANCE,
                    "rssi": rssi,
                }
            ]
        }
    )


def com_wifi(bssid: str | None = BSSID) -> str:
    return json.dumps({"wifi": [{"ssid": "Acme-Corp", "bssid": bssid}]})


def com_gps(metros_do_centro: float = 50, accuracy: float = 15) -> str:
    return json.dumps(
        {
            "gps": {
                "latitude": HANGAR_LAT + metros_do_centro / 111_320.0,
                "longitude": HANGAR_LON,
                "accuracy_m": accuracy,
            }
        }
    )


async def bater_ponto(
    client: AsyncClient,
    cenario: dict,
    *,
    evidence: str | None = None,
    cor: tuple[int, int, int] = FUNCIONARIO,
    entry_type: str | None = None,
    label: str | None = None,
    note: str | None = None,
    idempotency_key: str | None = None,
    client_recorded_at: datetime | None = None,
    headers: dict | None = None,
):
    data: dict[str, str] = {"evidence": evidence if evidence is not None else com_beacon()}
    if entry_type:
        data["entry_type"] = entry_type
    if label is not None:
        data["label"] = label
    if note is not None:
        data["note"] = note
    if idempotency_key:
        data["idempotency_key"] = idempotency_key
    if client_recorded_at:
        data["client_recorded_at"] = client_recorded_at.isoformat()

    return await client.post(
        "/api/v1/time-entries",
        headers=headers or cenario["app"],
        files={"selfie": ("selfie.png", stub_image(cor), "image/png")},
        data=data,
    )
