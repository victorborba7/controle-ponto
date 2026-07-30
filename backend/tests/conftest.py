"""Infraestrutura dos testes.

Roda contra um Postgres de verdade, num banco separado (`ponto_facial_test`),
e nao contra SQLite: o schema depende de pgvector e JSONB, entao um banco
substituto testaria algo diferente do que vai para producao.
"""

import uuid
from collections.abc import AsyncGenerator
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

from app.api.deps import get_storage
from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_session
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
