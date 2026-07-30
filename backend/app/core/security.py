"""Hashing de senhas.

Argon2id e o algoritmo recomendado atualmente para senhas: resistente a ataque
por GPU e por hardware dedicado, ao contrario de bcrypt e SHA.

A emissao e validacao de JWT entra na Etapa 2.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
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
