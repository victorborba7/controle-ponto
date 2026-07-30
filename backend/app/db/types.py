"""Tipos de coluna reutilizaveis."""

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


def enum_column(enum_class: type[StrEnum], name: str, length: int = 30) -> SAEnum:
    """Coluna de enum que grava o *value*, nao o *name*.

    Por padrao o SQLAlchemy persiste o nome do membro ("PENDING_REVIEW"),
    enquanto a API serializa o valor ("pending_review"). Isso deixaria o banco
    e a API falando dialetos diferentes — quem escrevesse um relatorio SQL a
    mao teria de lembrar de traduzir. `values_callable` alinha os dois.

    native_enum=False grava como VARCHAR com CHECK constraint em vez de um TYPE
    do Postgres: adicionar um valor novo vira um ALTER de constraint simples,
    sem a dor de mexer em ENUM nativo.
    """
    return SAEnum(
        enum_class,
        name=name,
        native_enum=False,
        length=length,
        values_callable=lambda enum: [member.value for member in enum],
    )
