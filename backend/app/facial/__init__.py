"""Reconhecimento facial, desacoplado do resto do sistema.

O restante do backend importa daqui e nunca de `insightface`. Trocar de modelo
— inclusive empurrar a inferencia para o aparelho na fase edge — deve ser
trocar a implementacao selecionada por `FACE_ENGINE`, sem tocar em endpoint,
servico ou modelo de dados.
"""

from functools import lru_cache

from app.core.config import settings
from app.facial.base import (
    BoundingBox,
    DetectedFace,
    FaceEmbedding,
    FaceEngine,
    FaceQuality,
    MatchCandidate,
    MatchOutcome,
    MatchResult,
    classify_score,
    cosine_similarity,
)
from app.facial.errors import (
    EngineUnavailableError,
    FacialError,
    ImageDecodeError,
    ImageTooLargeError,
    LowQualityImageError,
    MultipleFacesError,
    NoFaceDetectedError,
)
from app.facial.runner import AsyncFaceEngine


def build_engine(name: str) -> FaceEngine:
    """Instancia a engine pelo nome configurado."""
    if name == "stub":
        from app.facial.stub import StubFaceEngine

        return StubFaceEngine()

    if name == "insightface":
        from app.facial.insightface_engine import InsightFaceEngine

        return InsightFaceEngine()

    raise EngineUnavailableError(f"Engine facial desconhecida: {name!r}")


@lru_cache(maxsize=1)
def get_face_engine() -> AsyncFaceEngine:
    """Engine da aplicacao, instancia unica.

    Em cache porque a engine real carrega ~300 MB de pesos na memoria —
    reconstruir por requisicao seria inviavel.
    """
    return AsyncFaceEngine(build_engine(settings.face_engine))


__all__ = [
    "AsyncFaceEngine",
    "BoundingBox",
    "DetectedFace",
    "EngineUnavailableError",
    "FaceEmbedding",
    "FaceEngine",
    "FaceQuality",
    "FacialError",
    "ImageDecodeError",
    "ImageTooLargeError",
    "LowQualityImageError",
    "MatchCandidate",
    "MatchOutcome",
    "MatchResult",
    "MultipleFacesError",
    "NoFaceDetectedError",
    "build_engine",
    "classify_score",
    "cosine_similarity",
    "get_face_engine",
]
