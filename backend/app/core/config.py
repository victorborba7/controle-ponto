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

    # --- Reconhecimento facial ---
    # "stub" nao baixa modelo nenhum e e o padrao em desenvolvimento e testes.
    # "insightface" exige a imagem com requirements-facial.txt.
    face_engine: Literal["stub", "insightface"] = "stub"
    # Similaridade de cosseno sobre embeddings ArcFace normalizados.
    # Acima de match_threshold aprova; entre os dois manda para revisao do RH
    # (decisao D5); abaixo de review_threshold rejeita.
    face_match_threshold: float = 0.40
    face_review_threshold: float = 0.32
    # Quantas fotos o cadastro exige (decisao D4: varias absorvem mudanca de
    # luz, oculos e barba sem recadastro).
    face_min_enrollment_images: int = 3
    face_max_enrollment_images: int = 5

    # --- Armazenamento de imagens ---
    storage_path: str = "/app/storage"

    # --- CORS ---
    cors_origins: list[str] = ["http://localhost:3000"]

    @property
    def database_url_str(self) -> str:
        return str(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
