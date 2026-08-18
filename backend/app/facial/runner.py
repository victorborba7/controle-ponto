"""Fachada assincrona da engine.

Extrair um embedding leva de dezenas a centenas de milissegundos de CPU pura.
Chamado direto de um endpoint `async`, isso congela o event loop inteiro — a
API para de responder qualquer outra requisicao enquanto processa uma foto.

Esta classe despacha para uma thread. Endpoints devem usar sempre ela, nunca
a engine sincrona.
"""

from collections.abc import Sequence

import anyio.to_thread

from app.facial.base import (
    DetectedFace,
    FaceEmbedding,
    FaceEngine,
    MatchCandidate,
    MatchResult,
)


class AsyncFaceEngine:
    """Envolve uma FaceEngine sincrona, mantendo o event loop livre."""

    def __init__(self, engine: FaceEngine) -> None:
        self._engine = engine

    @property
    def engine(self) -> FaceEngine:
        return self._engine

    @property
    def name(self) -> str:
        return self._engine.name

    @property
    def version(self) -> str:
        return self._engine.version

    @property
    def embedding_dim(self) -> int:
        return self._engine.embedding_dim

    async def warmup(self) -> None:
        """Carrega o modelo agora, em thread, para nao pagar na primeira batida.

        Em thread pelo mesmo motivo das demais: a carga do ArcFace leva
        segundos de CPU pura, e no start da aplicacao o event loop precisa
        continuar respondendo o healthcheck — do contrario a plataforma
        conclui que a maquina nunca subiu e reverte o deploy.
        """
        await anyio.to_thread.run_sync(self._engine.warmup)

    async def detect(self, image: bytes) -> list[DetectedFace]:
        return await anyio.to_thread.run_sync(self._engine.detect, image)

    async def extract_embedding(self, image: bytes) -> FaceEmbedding:
        return await anyio.to_thread.run_sync(self._engine.extract_embedding, image)

    def verify(self, probe: Sequence[float], template: Sequence[float]) -> float:
        """Sincrono mesmo: comparar dois vetores de 512 floats e trivial.

        Mandar isto para uma thread custaria mais do que a propria conta.
        """
        return self._engine.verify(probe, template)

    def verify_against_templates(
        self,
        probe: Sequence[float],
        candidates: Sequence[MatchCandidate],
        *,
        match_threshold: float,
        review_threshold: float,
    ) -> MatchResult:
        return self._engine.verify_against_templates(
            probe,
            candidates,
            match_threshold=match_threshold,
            review_threshold=review_threshold,
        )

    def identify(
        self,
        probe: Sequence[float],
        candidates: Sequence[MatchCandidate],
        *,
        match_threshold: float,
        review_threshold: float,
    ) -> MatchResult:
        return self._engine.identify(
            probe,
            candidates,
            match_threshold=match_threshold,
            review_threshold=review_threshold,
        )
