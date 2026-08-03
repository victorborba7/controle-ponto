"""Como um ponto vira aprovado, pendente ou recusado.

Funcao pura, isolada da orquestracao de proposito: e a regra mais consequente
do sistema — decide se alguem recebe pelo dia trabalhado — e precisa ser
legivel e exercitavel sem foto, sem banco e sem rede.

O principio que a organiza e a decisao D5: **bloquear o funcionario de bater
ponto e pior que gerar um registro para o RH conferir.** Quem esta no lugar
certo, na hora certa, com o rosto certo, nao pode ser barrado porque a luz
estava ruim ou o GPS oscilou. Na duvida, registra e sinaliza.

A unica excecao e o rosto claramente diferente: ai nao ha duvida a resolver,
ha uma pessoa tentando bater o ponto de outra.
"""

from dataclasses import dataclass

from app.core.messages import Msg
from app.facial.base import MatchOutcome
from app.models.enums import TimeEntryStatus
from app.services.location_validator import LocationVerdict


@dataclass(frozen=True)
class EntryDecision:
    status: TimeEntryStatus
    #: Motivo tecnico, gravado no registro e lido pelo RH na conferencia.
    #: Fica em uma lingua so, de proposito: e trilha de auditoria, e trilha
    #: traduzida e trilha que nao se consegue procurar depois.
    reason: str
    #: Chave do texto que o app mostra ao funcionario. Fala de acao, nao de
    #: sistema. Resolvida na borda HTTP, no idioma do aparelho.
    chave: Msg

    @property
    def accepted(self) -> bool:
        """O ponto foi registrado (ainda que precise de conferencia)."""
        return self.status is not TimeEntryStatus.REJECTED


def decide(
    *,
    face_outcome: MatchOutcome,
    face_score: float | None,
    location: LocationVerdict,
    clock_skew_seconds: float = 0.0,
    max_clock_skew_seconds: int = 900,
) -> EntryDecision:
    """Combina reconhecimento facial e localizacao num desfecho."""
    # --- Rosto diferente: nao ha duvida a resolver ---
    if face_outcome is MatchOutcome.NO_MATCH:
        return EntryDecision(
            status=TimeEntryStatus.REJECTED,
            reason=(
                f"O rosto nao corresponde ao cadastro (score {face_score:.2f})"
                if face_score is not None
                else "O rosto nao corresponde ao cadastro"
            ),
            chave=Msg.ROSTO_NAO_RECONHECIDO,
        )

    pendencias: list[str] = []

    if face_outcome is MatchOutcome.REVIEW:
        pendencias.append(
            f"Reconhecimento facial no limite (score {face_score:.2f})"
            if face_score is not None
            else "Reconhecimento facial no limite"
        )

    if not location.accepted:
        pendencias.append(location.reason)
    elif location.inconsistencies:
        pendencias.extend(location.inconsistencies)

    if abs(clock_skew_seconds) > max_clock_skew_seconds:
        pendencias.append(_clock_skew_reason(clock_skew_seconds))

    if not pendencias:
        return EntryDecision(
            status=TimeEntryStatus.APPROVED,
            reason=location.reason,
            chave=Msg.PONTO_REGISTRADO,
        )

    return EntryDecision(
        status=TimeEntryStatus.PENDING_REVIEW,
        reason="; ".join(pendencias),
        chave=Msg.PONTO_EM_CONFERENCIA,
    )


def _clock_skew_reason(skew_seconds: float) -> str:
    """Explica a divergencia entre o relogio do aparelho e o do servidor.

    As duas direcoes contam historias diferentes: atraso costuma ser envio
    represado numa area sem sinal, enquanto um relogio adiantado nao tem
    explicacao inocente — o horario que vale e sempre o do servidor.
    """
    minutos = abs(skew_seconds) / 60
    if skew_seconds > 0:
        return (
            f"Registro enviado com {minutos:.0f} min de atraso; "
            "confira o horario real da batida"
        )
    return f"O relogio do aparelho esta {minutos:.0f} min adiantado"
