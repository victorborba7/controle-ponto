"""Regras de autenticacao: login, emissao, rotacao e revogacao de sessao."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    verify_password,
)
from app.models import Device, Employee, RefreshToken, Tenant, User
from app.models.enums import EmployeeStatus, SubjectType
from app.schemas.auth import DeviceInfo, TokenPair

# Hash descartavel usado para gastar o mesmo tempo de CPU quando o titular nao
# existe. Sem isso, "email inexistente" responde bem mais rapido que "senha
# errada", e a diferenca permite enumerar quem tem conta.
_DUMMY_HASH = hash_password("verificacao-de-tempo-constante")


class AuthError(Exception):
    """Falha de autenticacao.

    Mensagem sempre generica: distinguir "usuario nao existe" de "senha errada"
    entrega ao atacante metade do trabalho.
    """


def _now() -> datetime:
    return datetime.now(UTC)


async def _load_active_tenant(session: AsyncSession, slug: str) -> Tenant | None:
    return await session.scalar(
        select(Tenant).where(Tenant.slug == slug, Tenant.is_active.is_(True))
    )


# --------------------------------------------------------------------------
# Emissao de sessao
# --------------------------------------------------------------------------


async def issue_token_pair(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    subject_id: uuid.UUID,
    subject_type: SubjectType,
    role: str | None = None,
    device_id: uuid.UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[TokenPair, RefreshToken]:
    """Emite access + refresh e registra a sessao.

    Devolve tambem o registro do refresh token para quem precisar encadear a
    rotacao — evita ter de reconsultar o banco pelo hash logo em seguida.
    """
    access_token, expires_at = create_access_token(
        subject_id=subject_id,
        subject_type=subject_type.value,
        tenant_id=tenant_id,
        role=role,
        device_id=device_id,
    )

    raw_refresh = generate_refresh_token()
    now = _now()
    record = RefreshToken(
        tenant_id=tenant_id,
        token_hash=hash_refresh_token(raw_refresh),
        subject_type=subject_type,
        subject_id=subject_id,
        device_id=device_id,
        created_at=now,
        expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        created_ip=ip_address,
        user_agent=user_agent,
    )
    session.add(record)

    pair = TokenPair(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=int((expires_at - now).total_seconds()),
    )
    return pair, record


# --------------------------------------------------------------------------
# Login do painel administrativo
# --------------------------------------------------------------------------


async def authenticate_admin(
    session: AsyncSession,
    *,
    tenant_slug: str,
    email: str,
    password: str,
) -> tuple[User, Tenant]:
    tenant = await _load_active_tenant(session, tenant_slug)

    user: User | None = None
    if tenant is not None:
        user = await session.scalar(
            select(User).where(
                User.tenant_id == tenant.id,
                User.email == email.lower(),
                User.is_active.is_(True),
            )
        )

    # Verifica sempre, mesmo sem usuario, para o tempo de resposta nao denunciar
    # se o email existe.
    password_ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)

    if user is None or tenant is None or not password_ok:
        raise AuthError("Credenciais invalidas")

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    user.last_login_at = _now()
    return user, tenant


# --------------------------------------------------------------------------
# Login do app do funcionario
# --------------------------------------------------------------------------


async def authenticate_employee(
    session: AsyncSession,
    *,
    tenant_slug: str,
    external_code: str,
    password: str,
    device_info: DeviceInfo,
) -> tuple[Employee, Tenant, Device]:
    tenant = await _load_active_tenant(session, tenant_slug)

    employee: Employee | None = None
    if tenant is not None:
        employee = await session.scalar(
            select(Employee).where(
                Employee.tenant_id == tenant.id,
                Employee.external_code == external_code,
            )
        )

    stored_hash = employee.password_hash if employee and employee.password_hash else _DUMMY_HASH
    password_ok = verify_password(password, stored_hash)

    if employee is None or tenant is None or not password_ok:
        raise AuthError("Credenciais invalidas")

    # Desligado ou suspenso nao bate ponto. Checado depois da senha para nao
    # revelar o estado do vinculo a quem nao souber a credencial.
    if employee.status is not EmployeeStatus.ACTIVE:
        raise AuthError("Credenciais invalidas")

    if needs_rehash(stored_hash):
        employee.password_hash = hash_password(password)

    device = await _register_device(session, tenant.id, employee, device_info)
    employee.last_login_at = _now()

    return employee, tenant, device


async def _register_device(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    employee: Employee,
    device_info: DeviceInfo,
) -> Device:
    """Pareia o aparelho ao funcionario (cria no primeiro login, atualiza depois).

    Amarrar o ponto a um aparelho conhecido e o que impede uma credencial
    vazada de registrar presenca de qualquer celular.
    """
    device = await session.scalar(
        select(Device).where(
            Device.tenant_id == tenant_id,
            Device.device_fingerprint == device_info.fingerprint,
        )
    )

    if device is None:
        device = Device(
            tenant_id=tenant_id,
            employee_id=employee.id,
            device_fingerprint=device_info.fingerprint,
            platform=device_info.platform,
        )
        session.add(device)
    elif device.employee_id != employee.id:
        # Mesmo aparelho, outro funcionario: acontece de verdade (celular
        # emprestado, aparelho reaproveitado). Transferir o vinculo e correto —
        # os pontos ja registrados continuam apontando para o device, entao o
        # historico de quem usou antes nao se perde.
        device.employee_id = employee.id

    device.platform = device_info.platform
    device.model = device_info.model
    device.os_version = device_info.os_version
    device.app_version = device_info.app_version
    device.last_seen_at = _now()

    # `revoked_at` NAO e limpo aqui, e essa e a diferenca entre revogacao ser um
    # controle e ser um enfeite: antes, entrar com a senha reabilitava o
    # aparelho, entao revogar um celular roubado durava ate o ladrao tocar em
    # "entrar". Reabilitar e ato do RH, em `POST .../devices/{id}/authorize`.
    #
    # O login em si continua valendo — a pessoa entra e ve o proprio historico.
    # O que o aparelho revogado nao faz e bater ponto: quem barra e
    # `_ensure_device_trusted`, com uma mensagem que manda procurar o RH.

    await session.flush()
    return device


# --------------------------------------------------------------------------
# Rotacao e revogacao
# --------------------------------------------------------------------------


async def rotate_refresh_token(
    session: AsyncSession,
    *,
    raw_token: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> TokenPair:
    """Troca um refresh token por um par novo.

    Rotaciona a cada uso: o token apresentado e revogado e substituido. Isso
    limita a janela de um token interceptado e habilita a deteccao de reuso
    abaixo.
    """
    token_hash = hash_refresh_token(raw_token)
    stored = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))

    if stored is None:
        raise AuthError("Refresh token invalido")

    now = _now()

    if stored.revoked_at is not None:
        # Token ja gasto sendo reapresentado. Ou foi roubado e esta sendo
        # replicado, ou o legitimo vazou — nos dois casos nao da para saber
        # qual das duas pontas e a honesta. Derruba todas as sessoes do
        # titular e obriga login novo.
        await _revoke_all_for_subject(
            session, stored.tenant_id, stored.subject_type, stored.subject_id
        )
        # Commit explicito: a resposta sera 401 e o tratamento de erro da
        # requisicao faz rollback, o que desfaria justamente a revogacao — a
        # unica coisa que precisa sobreviver a esta requisicao.
        await session.commit()
        raise AuthError("Refresh token invalido")

    if stored.expires_at <= now:
        raise AuthError("Refresh token expirado")

    is_active, subject_role = await _resolve_subject(session, stored)
    if not is_active:
        # Titular desativado ou removido desde a emissao do token.
        stored.revoked_at = now
        await session.commit()  # mesma razao do commit acima
        raise AuthError("Refresh token invalido")

    pair, successor = await issue_token_pair(
        session,
        tenant_id=stored.tenant_id,
        subject_id=stored.subject_id,
        subject_type=stored.subject_type,
        role=subject_role,
        device_id=stored.device_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    stored.revoked_at = now
    # Encadeia o sucessor: com a cadeia registrada da para reconstruir a linha
    # do tempo de uma sessao ao investigar um roubo de token.
    await session.flush()
    stored.replaced_by_id = successor.id

    return pair


async def _resolve_subject(
    session: AsyncSession, stored: RefreshToken
) -> tuple[bool, str | None]:
    """Devolve (titular ainda ativo, papel para o novo token).

    Reconsultado a cada rotacao de proposito: desativar alguem passa a valer no
    proximo refresh, sem esperar a sessao expirar sozinha. Funcionario nao tem
    papel — o escopo dele ja vem de subject_type.
    """
    if stored.subject_type is SubjectType.USER:
        user = await session.scalar(
            select(User).where(User.id == stored.subject_id, User.is_active.is_(True))
        )
        return (user is not None), (user.role.value if user else None)

    employee = await session.scalar(
        select(Employee).where(
            Employee.id == stored.subject_id,
            Employee.status == EmployeeStatus.ACTIVE,
        )
    )
    return (employee is not None), None


async def _revoke_all_for_subject(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    subject_type: SubjectType,
    subject_id: uuid.UUID,
) -> None:
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.tenant_id == tenant_id,
            RefreshToken.subject_type == subject_type,
            RefreshToken.subject_id == subject_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=_now())
    )


async def revoke_refresh_token(session: AsyncSession, raw_token: str) -> None:
    """Logout. Silencioso se o token nao existir — nada a revelar."""
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == hash_refresh_token(raw_token),
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=_now())
    )
