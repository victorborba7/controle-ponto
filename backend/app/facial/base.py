"""Interface do reconhecimento facial.

Todo o resto do sistema fala com `FaceEngine` e nunca importa `insightface`
diretamente. E o que permite, na fase edge, trocar por um modelo rodando no
proprio aparelho sem reescrever o backend — e o que permite testar as etapas
seguintes sem baixar 300 MB de modelo.

**Os metodos sao sincronos e bloqueantes de proposito**: inferencia e trabalho
de CPU, nao de I/O, e fingir que e assincrono so esconderia que o event loop
fica parado durante a extracao. Endpoints devem usar `AsyncFaceEngine`
(em `app.facial.runner`), que despacha para uma thread.
"""

import math
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


@dataclass(frozen=True)
class BoundingBox:
    """Retangulo do rosto na imagem, em pixels."""

    x: int
    y: int
    width: int
    height: int

    @property
    def area(self) -> int:
        return self.width * self.height


@dataclass(frozen=True)
class FaceQuality:
    """Avaliacao da foto como fonte de biometria.

    Existe para barrar template ruim na origem: um embedding gerado de foto
    tremida ou de rosto pequeno demais gera falso negativo depois, e o
    funcionario e quem paga, tentando bater ponto que nao passa.
    """

    score: float
    sharpness: float
    face_ratio: float
    detection_score: float
    issues: tuple[str, ...] = ()

    @property
    def is_acceptable(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class DetectedFace:
    box: BoundingBox
    detection_score: float
    quality: FaceQuality


@dataclass(frozen=True)
class FaceEmbedding:
    """Representacao numerica do rosto.

    `vector` vem sempre normalizado (norma L2 = 1), o que faz a similaridade
    de cosseno ser um simples produto escalar e mantem os scores comparaveis
    entre fotos.

    Dado biometrico: nunca serializar isto numa resposta de API.
    """

    vector: tuple[float, ...]
    model_name: str
    model_version: str
    quality: FaceQuality
    box: BoundingBox | None = None

    def __repr__(self) -> str:
        # Sem os valores do vetor: evita dado biometrico cair em log de erro.
        return f"<FaceEmbedding {self.model_name}/{self.model_version} dim={len(self.vector)}>"


@dataclass(frozen=True)
class MatchCandidate:
    """Template cadastrado, para comparacao 1:N."""

    template_id: Any
    vector: Sequence[float]
    metadata: dict[str, Any] = field(default_factory=dict)


class MatchOutcome(StrEnum):
    MATCH = "match"
    REVIEW = "review"
    NO_MATCH = "no_match"


@dataclass(frozen=True)
class MatchResult:
    score: float
    outcome: MatchOutcome
    template_id: Any | None = None

    @property
    def is_match(self) -> bool:
        return self.outcome is MatchOutcome.MATCH


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Similaridade de cosseno, no intervalo [-1, 1].

    Normaliza os dois lados em vez de assumir que ja vieram normalizados: a
    funcao tambem e usada com vetores lidos do banco, e um template gravado por
    uma versao antiga poderia nao estar normalizado.
    """
    if len(a) != len(b):
        raise ValueError(f"Dimensoes incompativeis: {len(a)} != {len(b)}")

    dot = norm_a = norm_b = 0.0
    for va, vb in zip(a, b, strict=True):
        dot += va * vb
        norm_a += va * va
        norm_b += vb * vb

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def classify_score(
    score: float,
    *,
    match_threshold: float,
    review_threshold: float,
) -> MatchOutcome:
    """Traduz o score num desfecho.

    A faixa intermediaria (entre revisao e aprovacao) existe pela decisao D5:
    perto do limiar, registrar e mandar para conferencia do RH e melhor que
    barrar alguem que so estava com o rosto mal iluminado.
    """
    if match_threshold < review_threshold:
        raise ValueError("match_threshold deve ser maior ou igual a review_threshold")
    if score >= match_threshold:
        return MatchOutcome.MATCH
    if score >= review_threshold:
        return MatchOutcome.REVIEW
    return MatchOutcome.NO_MATCH


class FaceEngine(ABC):
    """Contrato de um modelo de reconhecimento facial."""

    #: Identificam qual modelo gerou cada template gravado. Permitem conviver
    #: com duas geracoes de embedding durante uma troca de modelo.
    name: str = "abstract"
    version: str = "0"
    embedding_dim: int = 512

    @abstractmethod
    def detect(self, image: bytes) -> list[DetectedFace]:
        """Localiza os rostos da imagem. Lista vazia se nao houver nenhum."""

    @abstractmethod
    def extract_embedding(self, image: bytes) -> FaceEmbedding:
        """Extrai o embedding do unico rosto da imagem.

        Levanta NoFaceDetectedError, MultipleFacesError ou LowQualityImageError.
        Exigir exatamente um rosto e proposital: com duas pessoas no quadro nao
        da para saber qual delas esta batendo ponto.
        """

    # ---- Comparacao ----
    # Concretas, e nao abstratas, porque cosseno serve para toda familia
    # ArcFace. Um modelo futuro com outra metrica sobrescreve.

    def verify(self, probe: Sequence[float], template: Sequence[float]) -> float:
        """Compara 1:1 — o rosto capturado contra o template de quem diz ser.

        Modo padrao do MVP (decisao D3): o funcionario ja esta autenticado no
        app, entao sabemos contra quem comparar. E mais preciso e mais seguro
        que varrer a base inteira.
        """
        return cosine_similarity(probe, template)

    def identify(
        self,
        probe: Sequence[float],
        candidates: Sequence[MatchCandidate],
        *,
        match_threshold: float,
        review_threshold: float,
    ) -> MatchResult:
        """Compara 1:N — descobre de quem e o rosto entre os candidatos.

        Nao usado no fluxo do MVP, mas e o que o modo quiosque (tablet na
        portaria, sem login individual) vai precisar na fase 2.
        """
        best_id: Any | None = None
        best_score = -1.0

        for candidate in candidates:
            score = self.verify(probe, candidate.vector)
            if score > best_score:
                best_score = score
                best_id = candidate.template_id

        if best_id is None:
            return MatchResult(score=0.0, outcome=MatchOutcome.NO_MATCH)

        outcome = classify_score(
            best_score,
            match_threshold=match_threshold,
            review_threshold=review_threshold,
        )
        return MatchResult(score=best_score, outcome=outcome, template_id=best_id)

    def verify_against_templates(
        self,
        probe: Sequence[float],
        candidates: Sequence[MatchCandidate],
        *,
        match_threshold: float,
        review_threshold: float,
    ) -> MatchResult:
        """Melhor match entre os varios templates de um mesmo funcionario.

        Cada pessoa tem de 3 a 5 templates (decisao D4) e basta um bater: e
        assim que se absorve mudanca de luz, oculos ou barba sem recadastro.
        Mecanicamente igual a `identify`, mas com intencao diferente — aqui
        todos os candidatos sao da mesma pessoa.
        """
        return self.identify(
            probe,
            candidates,
            match_threshold=match_threshold,
            review_threshold=review_threshold,
        )
