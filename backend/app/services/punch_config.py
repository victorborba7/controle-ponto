"""Configuracao de batida: leitura, validacao e aplicacao.

Concentra num lugar so a pergunta "o que esta empresa exige na batida?", para
que o servico de ponto nao precise conhecer os modos e o painel nao precise
duplicar a validacao.

A regra de ouro aqui: **a config decide o que e pedido, nunca o que ja foi
gravado**. Mudar a configuracao amanha nao pode invalidar nem reinterpretar um
ponto batido hoje.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.repository import TenantRepository
from app.models import PunchConfig, PunchLabel
from app.models.enums import EntryType, LabelMode, NoteMode
from app.models.punch_config import LABEL_MAX_LENGTH, NOTE_MAX_LENGTH


class PunchInputError(Exception):
    """O que o funcionario mandou nao satisfaz a configuracao da empresa.

    Carrega `user_message` porque o texto vai para a tela de quem esta com o
    celular na mao: "Escolha o tipo da batida" resolve, "422 Unprocessable
    Entity" nao.
    """

    def __init__(self, message: str, *, user_message: str) -> None:
        super().__init__(message)
        self.user_message = user_message


@dataclass(frozen=True)
class PunchInput:
    """O que sobrou depois de validar, pronto para virar registro."""

    label: str | None
    note: str | None
    #: Tipo vindo do rotulo escolhido. `None` deixa a deducao automatica valer.
    entry_type: EntryType | None


async def load(session: AsyncSession, repo: TenantRepository) -> PunchConfig | None:
    """Configuracao da empresa, com os rotulos ja carregados.

    Devolve `None` quando a empresa nunca configurou nada — que e o estado de
    quem so quer bater entrada e saida, e o padrao de fabrica.
    """
    consulta = repo.query(PunchConfig).options(selectinload(PunchConfig.labels)).limit(1)
    return (await session.execute(consulta)).scalars().first()


def active_labels(config: PunchConfig | None) -> list[PunchLabel]:
    """Rotulos que o funcionario pode escolher, na ordem que o RH definiu.

    Desativar em vez de apagar e o que preserva o historico: um rotulo que saiu
    de uso continua existindo nos pontos antigos, e some da tela de quem bate.
    """
    if config is None:
        return []
    return [rotulo for rotulo in config.labels if rotulo.is_active]


def resolve(
    config: PunchConfig | None,
    *,
    label: str | None,
    note: str | None,
) -> PunchInput:
    """Confere o que o app mandou contra o que a empresa configurou.

    Falha alto em vez de ignorar em silencio. Descartar uma observacao que o
    funcionario escreveu — porque a config nao pedia — apagaria a justificativa
    de um atraso sem ninguem ficar sabendo.
    """
    if config is None:
        return _sem_configuracao(label, note)

    return PunchInput(
        label=_resolver_rotulo(config, label),
        note=_resolver_nota(config, note),
        entry_type=_tipo_do_rotulo(config, label),
    )


def _sem_configuracao(label: str | None, note: str | None) -> PunchInput:
    """Empresa sem config: nao ha campo para preencher, e mandar um e erro."""
    if _limpo(label) or _limpo(note):
        raise PunchInputError(
            "Batida trouxe rotulo/observacao sem configuracao que os peca",
            user_message="Este ponto nao aceita observacao nem tipo. Atualize o app.",
        )
    return PunchInput(label=None, note=None, entry_type=None)


def _resolver_nota(config: PunchConfig, note: str | None) -> str | None:
    texto = _limpo(note)

    if config.note_mode is NoteMode.HIDDEN:
        if texto:
            raise PunchInputError(
                "Observacao enviada com note_mode=hidden",
                user_message="Este ponto nao aceita observacao.",
            )
        return None

    if not texto:
        if config.note_mode is NoteMode.REQUIRED:
            raise PunchInputError(
                "Observacao obrigatoria ausente",
                user_message=config.note_prompt or "Escreva uma observacao para continuar.",
            )
        return None

    if len(texto) > NOTE_MAX_LENGTH:
        raise PunchInputError(
            f"Observacao com {len(texto)} caracteres, teto {NOTE_MAX_LENGTH}",
            user_message=f"A observacao passa de {NOTE_MAX_LENGTH} caracteres.",
        )
    return texto


def _resolver_rotulo(config: PunchConfig, label: str | None) -> str | None:
    texto = _limpo(label)

    if config.label_mode is LabelMode.HIDDEN:
        if texto:
            raise PunchInputError(
                "Rotulo enviado com label_mode=hidden",
                user_message="Este ponto nao aceita tipo de batida.",
            )
        return None

    if not texto:
        if config.label_required:
            raise PunchInputError(
                "Rotulo obrigatorio ausente",
                user_message="Escolha o tipo da batida para continuar.",
            )
        return None

    if config.label_mode is LabelMode.FREE:
        if len(texto) > LABEL_MAX_LENGTH:
            raise PunchInputError(
                f"Rotulo com {len(texto)} caracteres, teto {LABEL_MAX_LENGTH}",
                user_message=f"O tipo da batida passa de {LABEL_MAX_LENGTH} caracteres.",
            )
        return texto

    # LIST: so vale o que o RH cadastrou. Aceitar texto livre aqui deixaria o
    # funcionario inventar um tipo que nao mapeia para jornada nenhuma.
    escolhido = _achar_rotulo(config, texto)
    if escolhido is None:
        raise PunchInputError(
            f"Rotulo {texto!r} nao esta entre as opcoes ativas",
            user_message="Este tipo de batida nao existe mais. Atualize o app e tente de novo.",
        )
    return escolhido.name


def _tipo_do_rotulo(config: PunchConfig, label: str | None) -> EntryType | None:
    """O tipo que a opcao escolhida carrega.

    So o modo LIST decide tipo. Em FREE o texto e descricao do funcionario, e
    deixar uma palavra digitada mexer na contagem de horas seria devolver a ele
    exatamente a escolha que a deducao automatica existe para evitar.
    """
    if config.label_mode is not LabelMode.LIST:
        return None

    texto = _limpo(label)
    if not texto:
        return None

    escolhido = _achar_rotulo(config, texto)
    return escolhido.entry_type if escolhido else None


def _achar_rotulo(config: PunchConfig, texto: str) -> PunchLabel | None:
    """Busca sem diferenciar maiusculas — o app manda o que exibiu, mas
    versoes antigas podem ter normalizado diferente."""
    alvo = texto.casefold()
    for rotulo in active_labels(config):
        if rotulo.name.casefold() == alvo:
            return rotulo
    return None


def _limpo(valor: str | None) -> str | None:
    """Texto sem espacos nas pontas; string vazia vira ausencia.

    Campo em branco e campo nao preenchido — tratar `"   "` como resposta
    valida deixaria passar uma observacao obrigatoria vazia.
    """
    if valor is None:
        return None
    texto = valor.strip()
    return texto or None
