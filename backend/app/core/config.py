"""Configuracao da aplicacao, carregada de variaveis de ambiente."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Aplicacao ---
    app_name: str = "Ponto Facial API"
    environment: Literal["local", "staging", "production"] = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # --- Banco de dados ---
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://ponto:ponto@db:5432/ponto_facial"
    )
    db_echo: bool = False

    # --- Seguranca (usado a partir da Etapa 2) ---
    jwt_secret: str = Field(default="troque-em-producao", min_length=8)
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 30

    # --- Reconhecimento facial (Etapa 3) ---
    # "stub" nao baixa modelo nenhum: e o padrao ate a engine real entrar.
    face_engine: Literal["stub", "insightface"] = "stub"
    face_match_threshold: float = 0.40
    face_review_threshold: float = 0.32

    # --- CORS ---
    cors_origins: list[str] = ["http://localhost:3000"]

    @property
    def database_url_str(self) -> str:
        return str(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
