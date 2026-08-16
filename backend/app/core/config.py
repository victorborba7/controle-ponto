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

    # Ligar apenas quando a API estiver atras de um proxy por onde passa
    # *todo* acesso (Railway, Fly.io, CDN). Com ela desligada e um proxy no
    # caminho, o endereco do cliente e tratado como desconhecido — ver
    # `app.core.net.client_ip`.
    trust_proxy_headers: bool = False

    # --- Limite de tentativas de login ---
    # Matricula e um numero curto e adivinhavel ("0001"), e a senha inicial e
    # definida pelo RH. Sem teto, tentar todas as combinacoes e so questao de
    # tempo de CPU — e cada tentativa ainda queima um hash Argon2 do servidor.
    login_max_failures: int = 5
    login_failure_window_seconds: int = 900
    # Muitas identidades diferentes falhando do mesmo endereco e o padrao de
    # quem testa uma senha provavel contra a empresa inteira — ataque que o teto
    # por identidade nao pega, porque cada conta falha uma vez so.
    login_spray_max_identities: int = 10

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

    # --- Registro de ponto ---
    # Duas batidas seguidas dentro deste intervalo sao o mesmo toque repetido,
    # nao dois eventos.
    time_entry_min_interval_seconds: int = 60
    # Divergencia tolerada entre o relogio do aparelho e o do servidor. Acima
    # disso o registro vai para revisao: ou o envio ficou preso numa area sem
    # sinal, ou o relogio do celular foi ajustado.
    time_entry_max_clock_skew_seconds: int = 900

    # --- Armazenamento de imagens ---
    storage_path: str = "/app/storage"
    # Chave AES-256 em base64 (32 bytes) para criptografar as imagens de rosto
    # em repouso. Obrigatoria: imagem de rosto e dado biometrico, e gravar em
    # claro nao e aceitavel nem em desenvolvimento. Gerar com:
    #   python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"
    storage_encryption_key: str = Field(min_length=44)

    # --- CORS ---
    cors_origins: list[str] = ["http://localhost:3000"]

    @property
    def database_url_str(self) -> str:
        return str(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
