"""Configuracao de batida de ponto.

O RH monta; o app do funcionario le a versao reduzida para saber o que
desenhar na tela.
"""

import uuid

from fastapi import APIRouter, Depends, Request

from app.api.deps import CurrentAdmin, CurrentPrincipal, SessionDep, TenantRepo, require_roles
from app.models import PunchConfig, PunchLabel
from app.models.enums import AuditAction, UserRole
from app.schemas.punch_config import (
    PunchConfigOut,
    PunchConfigUpdate,
    PunchFormConfig,
    PunchFormLabel,
    PunchLabelOut,
)
from app.services import audit
from app.services import punch_config as service

router = APIRouter(prefix="/punch-config", tags=["configuracao de batida"])

ESCRITA = [Depends(require_roles(UserRole.OWNER, UserRole.HR))]

#: Como fica quem nunca configurou nada: batida simples, sem campo nenhum.
PADRAO = PunchConfigOut(
    note_mode="hidden",
    note_prompt=None,
    label_mode="hidden",
    label_required=False,
    labels=[],
)


@router.get("", response_model=PunchConfigOut)
async def get_config(
    _: CurrentAdmin,
    session: SessionDep,
    repo: TenantRepo,
) -> PunchConfigOut:
    """Configuracao atual da empresa, para a tela do RH."""
    config = await service.load(session, repo)
    if config is None:
        return PADRAO

    return PunchConfigOut(
        note_mode=config.note_mode,
        note_prompt=config.note_prompt,
        label_mode=config.label_mode,
        label_required=config.label_required,
        # Ordenados aqui e nao no banco porque a posicao e o que o RH arrastou;
        # inativos vem junto, que e o que distingue esta visao da do app.
        labels=[
            PunchLabelOut.model_validate(rotulo)
            for rotulo in sorted(config.labels, key=lambda r: r.position)
        ],
    )


@router.put("", response_model=PunchConfigOut, dependencies=ESCRITA)
async def update_config(
    principal: CurrentAdmin,
    session: SessionDep,
    repo: TenantRepo,
    payload: PunchConfigUpdate,
    request: Request,
) -> PunchConfigOut:
    """Substitui a configuracao inteira.

    Substituicao, e nao mesclagem: a ordem dos rotulos e o indice na lista
    enviada, o que deixa o RH reordenar arrastando sem precisar de endpoint
    proprio para isso.
    """
    config = await service.load(session, repo)
    if config is None:
        config = PunchConfig(
            note_mode=payload.note_mode,
            label_mode=payload.label_mode,
            # `labels=[]` explicito: sem isso a colecao fica nao-carregada e o
            # primeiro acesso apos o flush tenta um SELECT sincrono, que em
            # sessao assincrona estoura com MissingGreenlet.
            labels=[],
        )
        repo.add(config)
        await repo.flush()

    config.note_mode = payload.note_mode
    config.note_prompt = payload.note_prompt
    config.label_mode = payload.label_mode
    config.label_required = payload.label_required

    _substituir_rotulos(config, payload, tenant_id=principal.tenant_id)

    await session.flush()
    await audit.record_for(
        session,
        principal,
        action=AuditAction.UPDATE,
        entity_type="punch_config",
        entity_id=config.id,
        payload={
            "note_mode": payload.note_mode,
            "label_mode": payload.label_mode,
            "label_required": payload.label_required,
            "labels": [rotulo.name for rotulo in payload.labels],
        },
        description="Configuracao de batida alterada",
        ip_address=request.client.host if request.client else None,
    )
    await session.commit()
    await session.refresh(config)

    return await get_config(principal, session, repo)


@router.get("/form", response_model=PunchFormConfig)
async def get_form_config(
    _: CurrentPrincipal,
    session: SessionDep,
    repo: TenantRepo,
) -> PunchFormConfig:
    """O que o app precisa para montar a tela de batida.

    Aberto a qualquer autenticado do tenant, e nao so ao funcionario: o painel
    tambem usa para pre-visualizar como a tela vai ficar.
    """
    config = await service.load(session, repo)
    if config is None:
        return PunchFormConfig(
            note_mode="hidden",
            note_prompt=None,
            label_mode="hidden",
            label_required=False,
            labels=[],
        )

    return PunchFormConfig(
        note_mode=config.note_mode,
        note_prompt=config.note_prompt,
        label_mode=config.label_mode,
        label_required=config.label_required,
        labels=[PunchFormLabel(name=rotulo.name) for rotulo in service.active_labels(config)],
    )


def _substituir_rotulos(
    config: PunchConfig,
    payload: PunchConfigUpdate,
    *,
    tenant_id: uuid.UUID,
) -> None:
    """Reescreve a lista de rotulos preservando a identidade dos que ficaram.

    Casar pelo nome em vez de apagar tudo e recriar importa: o id do rotulo
    aparece na trilha de auditoria, e recriar a cada salvamento encheria o
    historico de exclusoes e criacoes que nunca aconteceram de fato.
    """
    existentes = {rotulo.name.casefold(): rotulo for rotulo in config.labels}
    novos: list[PunchLabel] = []

    for posicao, entrada in enumerate(payload.labels):
        nome = entrada.name.strip()
        atual = existentes.pop(nome.casefold(), None)

        if atual is None:
            atual = PunchLabel(tenant_id=tenant_id, config_id=config.id, name=nome)
        atual.name = nome
        atual.entry_type = entrada.entry_type
        atual.is_active = entrada.is_active
        atual.position = posicao
        novos.append(atual)

    # `delete-orphan` no relacionamento apaga o que saiu da lista.
    config.labels = novos
