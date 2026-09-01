"""Primitivas de seguranca: hash de senha, JWT de acesso e refresh tokens.

Modelo de sessao em duas partes:

- **Access token**: JWT curto (30 min), sem estado. Rapido de validar em toda
  requisicao, mas impossivel de revogar antes de expirar.
- **Refresh token**: string opaca e aleatoria, guardada com hash no banco.
  Longa duracao, revogavel na hora.

A combinacao da o melhor dos dois: validacao barata no caminho quente e poder
de corte imediato quando um aparelho e roubado ou alguem e desligado.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings

_hasher = PasswordHasher()

ACCESS_TOKEN_TYPE = "access"


# --------------------------------------------------------------------------
# Senhas
# --------------------------------------------------------------------------

#: Tamanho minimo de qualquer senha do sistema, para os dois publicos.
#:
#: Igual para quem administra e para quem bate ponto, por decisao do time.
#: O painel exigia 12 e o app 6, e duas regras para a mesma coisa fazem o RH
#: concluir que o sistema esta com defeito quando uma senha aceita num lugar e
#: recusada no outro.
#:
#: Doze e alto para uma matricula de chao de fabrica, e essa e a escolha: uma
#: conta de funcionario abre a porta para bater ponto no lugar de outra pessoa,
#: entao o rigor nao deveria depender de quem a usa.
#:
#: **Vale so na definicao.** Senha ja gravada continua funcionando: o hash nao
#: guarda o tamanho, e forcar troca em massa custaria mais do que resolve.
SENHA_MINIMA = 12


def hash_password(password: str) -> str:
    """Argon2id: resistente a ataque por GPU e hardware dedicado."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Confere a senha. Retorna False em vez de levantar excecao.

    Nao distingue "senha errada" de "hash corrompido" de proposito: qualquer
    diferenciacao aqui vira canal lateral para quem estiver sondando o login.
    """
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Indica se o hash foi gerado com parametros defasados.

    Chamar no login bem-sucedido: permite endurecer os parametros do Argon2 no
    futuro e migrar as senhas existentes conforme cada usuario entra.
    """
    try:
        return _hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, ValueError):
        return True


# --------------------------------------------------------------------------
# Access token (JWT)
# --------------------------------------------------------------------------


def create_access_token(
    *,
    subject_id: uuid.UUID,
    subject_type: str,
    tenant_id: uuid.UUID,
    role: str | None = None,
    device_id: uuid.UUID | None = None,
) -> tuple[str, datetime]:
    """Emite o JWT de acesso. Devolve (token, instante de expiracao).

    O `tid` (tenant) vai dentro do token assinado justamente para que o escopo
    da requisicao nao dependa de nada que o cliente possa alterar.
    """
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.access_token_ttl_minutes)

    claims: dict[str, Any] = {
        "sub": str(subject_id),
        "typ": ACCESS_TOKEN_TYPE,
        "styp": subject_type,
        "tid": str(tenant_id),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    if role is not None:
        claims["role"] = role
    if device_id is not None:
        claims["did"] = str(device_id)

    token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Valida assinatura e expiracao. Retorna None se o token nao presta.

    `algorithms` fixo na lista configurada e obrigatorio: aceitar o algoritmo
    que vem no cabecalho do proprio token abre a porta para o ataque de trocar
    a assinatura por "alg: none".
    """
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "tid"]},
        )
    except jwt.PyJWTError:
        return None

    # Um refresh token nunca deve ser aceito como credencial de acesso.
    if claims.get("typ") != ACCESS_TOKEN_TYPE:
        return None
    return claims


# --------------------------------------------------------------------------
# Refresh token (opaco)
# --------------------------------------------------------------------------


def generate_refresh_token() -> str:
    """Gera um refresh token aleatorio.

    Opaco em vez de JWT: nao precisa carregar informacao nenhuma, ja que a
    validacao consulta o banco de qualquer forma para checar revogacao. Menos
    superficie, nada que vaze se o token for interceptado.
    """
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """SHA-256 do refresh token, que e o que vai para o banco.

    SHA-256 basta aqui — diferente de senha. O token ja tem 48 bytes de
    entropia aleatoria, entao nao existe dicionario a forcar; o hash serve
    apenas para que um vazamento da tabela nao entregue sessoes ativas.
    """
    return hashlib.sha256(token.encode()).hexdigest()
