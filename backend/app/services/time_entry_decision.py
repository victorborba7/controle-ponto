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

from app.facial.base import MatchOutcome
from app.models.enums import TimeEntryStatus
from app.services.location_validator import LocationVerdict


@dataclass(frozen=True)
class EntryDecision:
    status: TimeEntryStatus
    reason: str
    #: Texto para o app mostrar ao funcionario. Fala de acao, nao de sistema.
    message: str

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
            message="Nao reconhecemos seu rosto. Tente novamente com melhor iluminacao.",
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
            message="Ponto registrado.",
        )

    return EntryDecision(
        status=TimeEntryStatus.PENDING_REVIEW,
        reason="; ".join(pendencias),
        message="Ponto registrado e enviado para conferencia do RH.",
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
