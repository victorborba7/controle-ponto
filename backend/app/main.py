"""Ponto de entrada da API."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, employees, face_templates, health, sites, time_entries
from app.core.config import settings
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
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
app.include_router(sites.router, prefix=settings.api_v1_prefix)
app.include_router(time_entries.router, prefix=settings.api_v1_prefix)
