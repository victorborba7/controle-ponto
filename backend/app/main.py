"""Ponto de entrada da API."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    auth,
    employees,
    face_templates,
    health,
    punch_config,
    sites,
    time_entries,
)
from app.core.config import settings
from app.db.session import engine
from app.facial import get_face_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # O primeiro uso da engine carrega o modelo, e isso leva segundos. Sem
    # antecipar aqui, quem paga a conta e o primeiro funcionario a bater ponto
    # depois de cada deploy — alguem parado na porta do hangar as 7h.
    #
    # Falha NAO derruba o start: sem modelo a API ainda serve /health, login e
    # consulta de registros, e so o reconhecimento facial fica indisponivel.
    # Abortar aqui faria a maquina nunca ficar saudavel e reverteria o deploy
    # inteiro por causa de um subsistema.
    try:
        await get_face_engine().warmup()
    except Exception:
        logger.exception("Falha ao pre-carregar a engine facial; seguindo sem ela.")

    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# /health fica fora do prefixo versionado: infra costuma esperar na raiz.
app.include_router(health.router)

app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(employees.router, prefix=settings.api_v1_prefix)
app.include_router(face_templates.router, prefix=settings.api_v1_prefix)
app.include_router(punch_config.router, prefix=settings.api_v1_prefix)
app.include_router(sites.router, prefix=settings.api_v1_prefix)
app.include_router(time_entries.router, prefix=settings.api_v1_prefix)
