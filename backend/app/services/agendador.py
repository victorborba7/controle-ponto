"""Agendador do lembrete horario.

Roda **dentro do processo da API**, e nao como worker separado. Com uma maquina
so, sem fila e um job que faz um SELECT a cada poucos minutos, um segundo
processo no Fly dobraria o custo de infraestrutura para nada.

O preco dessa escolha esta em `models/reminder.py`: como o processo reinicia a
cada implantacao, o estado do que ja foi lembrado vive no banco, nao aqui.

**Desligado por padrao.** Precisa de `SCHEDULER_ENABLED=true`, que fica no
fly.toml e em lugar nenhum mais — do contrario a suite de testes e qualquer
`docker compose up` de desenvolvimento comecariam a disparar push de verdade
para aparelhos de verdade.
"""

import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.services import lembretes

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _rodada() -> None:
    """Uma passada do agendador. Nunca levanta excecao para fora.

    Se levantasse, o APScheduler removeria o job depois de algumas falhas e o
    lembrete morreria em silencio ate a proxima implantacao.
    """
    try:
        async with AsyncSessionLocal() as session:
            enviados = await lembretes.executar(session, datetime.now(UTC))
            await session.commit()
        if enviados:
            logger.info("Lembretes enviados: %d", enviados)
    except Exception:
        logger.exception("Falha na rodada de lembretes")


def iniciar() -> None:
    global _scheduler

    if not settings.scheduler_enabled:
        logger.info("Agendador desligado (SCHEDULER_ENABLED=false).")
        return

    if _scheduler is not None:
        return

    _scheduler = AsyncIOScheduler(timezone="UTC")
    # A cada 5 minutos, e nao de hora em hora: a hora de cada funcionario conta
    # a partir da entrada dele, entao "hora cheia" cai em minutos diferentes
    # para cada um. Cinco minutos e a resolucao do atraso maximo do lembrete.
    _scheduler.add_job(
        _rodada,
        "interval",
        minutes=settings.scheduler_interval_minutes,
        id="lembretes_de_batida",
        # Rodada atrasada nao se acumula: se a maquina travou, interessa o
        # estado de agora, nao repetir as passadas perdidas.
        coalesce=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info(
        "Agendador de lembretes ligado (a cada %d min).",
        settings.scheduler_interval_minutes,
    )


def parar() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
