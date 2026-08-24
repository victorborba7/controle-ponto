"""Usuarios do painel: quem administra a empresa.

Nao confundir com `employees`, que sao as pessoas que batem ponto. Sao tabelas
e publicos separados, com permissoes disjuntas — um funcionario nunca acessa o
painel, e um usuario do painel nunca bate ponto.

**So OWNER gerencia usuarios.** Se HR pudesse, uma conta de HR criaria uma
conta OWNER e a distincao de papeis nao significaria nada.
"""

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import (
    CurrentAdmin,
    Locale,
    SessionDep,
    TenantRepo,
    erro_http,
    require_roles,
)
from app.core.messages import Msg
from app.core.net import client_ip
from app.core.security import hash_password
from app.models import User
from app.models.enums import AuditAction, UserRole
from app.schemas.user import (
    UserCreate,
    UserList,
    UserPasswordReset,
    UserSummary,
    UserUpdate,
)
from app.services import audit

router = APIRouter(prefix="/users", tags=["usuarios do painel"])

#: Ler a lista serve a qualquer perfil do painel — saber quem tem acesso nao e
#: privilegio. Escrever e so do dono.
SO_PROPRIETARIO = [Depends(require_roles(UserRole.OWNER))]


async def _buscar(repo: TenantRepo, user_id: uuid.UUID, idioma: str) -> User:
    usuario = await repo.get(User, user_id)
    if usuario is None:
        raise erro_http(status.HTTP_404_NOT_FOUND, Msg.USUARIO_NAO_ENCONTRADO, idioma)
    return usuario


async def _contar_proprietarios_ativos(repo: TenantRepo) -> int:
    resultado = await repo.session.scalar(
        select(func.count())
        .select_from(User)
        .where(
            User.tenant_id == repo.tenant_id,
            User.role == UserRole.OWNER,
            User.is_active.is_(True),
        )
    )
    return resultado or 0


@router.get("", response_model=UserList)
async def listar(principal: CurrentAdmin, repo: TenantRepo) -> UserList:
    """Quem tem acesso ao painel desta empresa."""
    resultado = await repo.session.execute(
        repo.query(User).order_by(User.name)
    )
    return UserList(items=[UserSummary.model_validate(u) for u in resultado.scalars().all()])


@router.post(
    "",
    response_model=UserSummary,
    status_code=status.HTTP_201_CREATED,
    dependencies=SO_PROPRIETARIO,
)
async def criar(
    payload: UserCreate,
    principal: CurrentAdmin,
    repo: TenantRepo,
    session: SessionDep,
    request: Request,
    idioma: Locale,
) -> UserSummary:
    """Cria um usuario do painel com a senha inicial que voce definir."""
    usuario = User(
        tenant_id=repo.tenant_id,
        email=payload.email.lower(),
        name=payload.name,
        role=payload.role,
        password_hash=hash_password(payload.password),
    )
    session.add(usuario)

    try:
        await session.flush()
    except IntegrityError as exc:
        # Email e unico POR TENANT (uq_users_tenant_email). Traduzir aqui em vez
        # de consultar antes evita a corrida entre duas criacoes simultaneas.
        await session.rollback()
        raise erro_http(status.HTTP_409_CONFLICT, Msg.EMAIL_JA_USADO, idioma) from exc

    await audit.record_for(
        session,
        principal,
        action=AuditAction.CREATE,
        entity_type="user",
        entity_id=usuario.id,
        payload={"email": usuario.email, "papel": usuario.role.value},
        description=f"Usuario do painel criado: {usuario.name}",
        ip_address=client_ip(request),
    )
    await session.commit()

    return UserSummary.model_validate(usuario)


@router.patch("/{user_id}", response_model=UserSummary, dependencies=SO_PROPRIETARIO)
async def atualizar(
    user_id: uuid.UUID,
    payload: UserUpdate,
    principal: CurrentAdmin,
    repo: TenantRepo,
    session: SessionDep,
    request: Request,
    idioma: Locale,
) -> UserSummary:
    """Altera nome, papel ou situacao.

    Duas travas contra tranca-se para fora, e as duas ja aconteceram em produtos
    reais: ninguem rebaixa nem desativa a si mesmo, e o ultimo proprietario ativo
    nao pode deixar de ser proprietario. Sem a segunda, uma empresa fica sem
    quem gerencie acesso e a saida e chamar o fornecedor.
    """
    usuario = await _buscar(repo, user_id, idioma)

    mexendo_em_si = usuario.id == principal.subject_id
    mudando_papel = payload.role is not None and payload.role != usuario.role
    desativando = payload.is_active is False and usuario.is_active

    if mexendo_em_si and (mudando_papel or desativando):
        raise erro_http(status.HTTP_409_CONFLICT, Msg.NAO_PODE_MUDAR_A_SI_MESMO, idioma)

    perde_proprietario = usuario.role is UserRole.OWNER and (mudando_papel or desativando)
    if perde_proprietario and await _contar_proprietarios_ativos(repo) <= 1:
        raise erro_http(status.HTTP_409_CONFLICT, Msg.ULTIMO_PROPRIETARIO, idioma)

    antes = {"papel": usuario.role.value, "ativo": usuario.is_active}

    if payload.name is not None:
        usuario.name = payload.name
    if payload.role is not None:
        usuario.role = payload.role
    if payload.is_active is not None:
        usuario.is_active = payload.is_active

    await audit.record_for(
        session,
        principal,
        action=AuditAction.UPDATE,
        entity_type="user",
        entity_id=usuario.id,
        payload={
            "antes": antes,
            "depois": {"papel": usuario.role.value, "ativo": usuario.is_active},
        },
        description=f"Usuario do painel alterado: {usuario.name}",
        ip_address=client_ip(request),
    )
    await session.commit()

    return UserSummary.model_validate(usuario)


@router.post(
    "/{user_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=SO_PROPRIETARIO,
)
async def redefinir_senha(
    user_id: uuid.UUID,
    payload: UserPasswordReset,
    principal: CurrentAdmin,
    repo: TenantRepo,
    session: SessionDep,
    request: Request,
    idioma: Locale,
) -> None:
    """Define uma senha nova para outro usuario do painel.

    **Nao revoga as sessoes ativas dele.** O motivo de uso normal e "esqueci a
    senha", e derrubar a pessoa do painel enquanto ela trabalha resolveria um
    problema criando outro. Para cortar acesso de verdade, desative a conta —
    o login checa `is_active` e a sessao morre na proxima renovacao.
    """
    usuario = await _buscar(repo, user_id, idioma)

    usuario.password_hash = hash_password(payload.password)

    await audit.record_for(
        session,
        principal,
        action=AuditAction.UPDATE,
        entity_type="user",
        entity_id=usuario.id,
        description=f"Senha redefinida para {usuario.name}",
        ip_address=client_ip(request),
    )
    await session.commit()
