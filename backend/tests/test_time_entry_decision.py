"""Como um ponto vira aprovado, pendente ou recusado.

Testes de mesa da regra mais consequente do sistema: ela decide se alguem
recebe pelo dia trabalhado. Sem foto, sem banco, sem rede.
"""

import uuid

import pytest

from app.core.messages import Msg
from app.facial.base import MatchOutcome
from app.models.enums import LocationMethod, TimeEntryStatus
from app.services.location_validator import LocationVerdict
from app.services.time_entry_decision import decide


def local_confirmado(
    *, inconsistencies: tuple[str, ...] = (), method: LocationMethod = LocationMethod.BEACON
) -> LocationVerdict:
    return LocationVerdict(
        method=method,
        confidence=0.9,
        accepted=True,
        reason="Beacon Portao A detectado a -55 dBm",
        site_id=uuid.uuid4(),
        inconsistencies=inconsistencies,
    )


def sem_local() -> LocationVerdict:
    return LocationVerdict(
        method=LocationMethod.NONE,
        confidence=0.0,
        accepted=False,
        reason="O aparelho nao reportou nenhum sinal de localizacao",
    )


# --------------------------------------------------------------------------
# Caminho aprovado
# --------------------------------------------------------------------------


def test_rosto_certo_e_local_confirmado_aprova():
    decisao = decide(face_outcome=MatchOutcome.MATCH, face_score=0.88, location=local_confirmado())

    assert decisao.status is TimeEntryStatus.APPROVED
    assert decisao.accepted
    assert decisao.chave is Msg.PONTO_REGISTRADO


# --------------------------------------------------------------------------
# Rosto diferente: a unica recusa
# --------------------------------------------------------------------------


def test_rosto_diferente_recusa():
    """Nao ha duvida a resolver — ha alguem tentando bater o ponto de outro."""
    decisao = decide(
        face_outcome=MatchOutcome.NO_MATCH, face_score=0.08, location=local_confirmado()
    )

    assert decisao.status is TimeEntryStatus.REJECTED
    assert not decisao.accepted
    assert "0.08" in decisao.reason


def test_rosto_diferente_recusa_mesmo_com_tudo_mais_perfeito():
    """Localizacao impecavel nao compensa rosto de outra pessoa."""
    decisao = decide(
        face_outcome=MatchOutcome.NO_MATCH,
        face_score=0.05,
        location=local_confirmado(),
        clock_skew_seconds=0,
    )
    assert decisao.status is TimeEntryStatus.REJECTED


def test_mensagem_da_recusa_orienta_o_funcionario():
    """O texto fala de acao, nao de sistema."""
    decisao = decide(
        face_outcome=MatchOutcome.NO_MATCH, face_score=0.1, location=local_confirmado()
    )
    assert decisao.chave is Msg.ROSTO_NAO_RECONHECIDO


# --------------------------------------------------------------------------
# Pendencias: registra e sinaliza (decisao D5)
# --------------------------------------------------------------------------


def test_rosto_no_limite_vai_para_revisao():
    """Barrar quem esta no lugar certo por causa da luz e pior que revisar."""
    decisao = decide(face_outcome=MatchOutcome.REVIEW, face_score=0.36, location=local_confirmado())

    assert decisao.status is TimeEntryStatus.PENDING_REVIEW
    assert decisao.accepted
    assert "limite" in decisao.reason


def test_sem_localizacao_vai_para_revisao():
    decisao = decide(face_outcome=MatchOutcome.MATCH, face_score=0.9, location=sem_local())

    assert decisao.status is TimeEntryStatus.PENDING_REVIEW
    assert "nao reportou nenhum sinal" in decisao.reason


def test_incoerencia_entre_sinais_vai_para_revisao():
    """Beacon confirmando o hangar com GPS em outra cidade."""
    decisao = decide(
        face_outcome=MatchOutcome.MATCH,
        face_score=0.9,
        location=local_confirmado(
            inconsistencies=("O sinal indica Hangar, mas o aparelho esta a 100.0 km dali",)
        ),
    )

    assert decisao.status is TimeEntryStatus.PENDING_REVIEW
    assert "100.0 km" in decisao.reason


def test_pendencias_se_acumulam_na_justificativa():
    """O RH precisa ver tudo que pesou, nao so o primeiro problema."""
    decisao = decide(face_outcome=MatchOutcome.REVIEW, face_score=0.35, location=sem_local())

    assert "limite" in decisao.reason
    assert "nenhum sinal" in decisao.reason


# --------------------------------------------------------------------------
# Divergencia de relogio
# --------------------------------------------------------------------------


def test_pequena_divergencia_de_relogio_nao_atrapalha():
    decisao = decide(
        face_outcome=MatchOutcome.MATCH,
        face_score=0.9,
        location=local_confirmado(),
        clock_skew_seconds=120,
        max_clock_skew_seconds=900,
    )
    assert decisao.status is TimeEntryStatus.APPROVED


def test_envio_atrasado_vai_para_revisao():
    """Batida presa numa area sem sinal e enviada horas depois."""
    decisao = decide(
        face_outcome=MatchOutcome.MATCH,
        face_score=0.9,
        location=local_confirmado(),
        clock_skew_seconds=7200,
        max_clock_skew_seconds=900,
    )

    assert decisao.status is TimeEntryStatus.PENDING_REVIEW
    assert "atraso" in decisao.reason
    assert "120 min" in decisao.reason


def test_relogio_adiantado_e_descrito_diferente():
    """Atraso tem explicacao inocente; relogio adiantado nao tem."""
    decisao = decide(
        face_outcome=MatchOutcome.MATCH,
        face_score=0.9,
        location=local_confirmado(),
        clock_skew_seconds=-3600,
        max_clock_skew_seconds=900,
    )

    assert decisao.status is TimeEntryStatus.PENDING_REVIEW
    assert "adiantado" in decisao.reason


# --------------------------------------------------------------------------
# Confianca baixa nao reprova sozinha
# --------------------------------------------------------------------------


@pytest.mark.parametrize("metodo", [LocationMethod.BEACON, LocationMethod.WIFI, LocationMethod.GPS])
def test_qualquer_metodo_confirmado_aprova(metodo: LocationMethod):
    """GPS prova menos que beacon, mas confirmado e confirmado.

    A diferenca fica registrada na confianca, para o RH pesar depois — nao em
    barrar quem bateu ponto pelo elo mais fraco da cadeia.
    """
    decisao = decide(
        face_outcome=MatchOutcome.MATCH,
        face_score=0.9,
        location=local_confirmado(method=metodo),
    )
    assert decisao.status is TimeEntryStatus.APPROVED
