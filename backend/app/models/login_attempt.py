"""LoginAttempt — contador de falhas de autenticacao.

## Por que uma tabela, e nao memoria

Contador em memoria zera a cada deploy e nao e compartilhado entre workers: com
dois processos e um `restart`, o bloqueio vira sugestao. Como login e evento
raro, o custo de uma consulta por tentativa e irrelevante perto de ter um
controle que realmente vale.

## Por que esta e a unica tabela sem `tenant_id`

O principio da casa e que toda tabela de negocio carregue o tenant. Esta nao e
de negocio: ela conta tentativas que **podem nao ter tenant nenhum** — quem
sonda a API chuta o slug da empresa junto com o resto. Amarrar a um tenant
existente deixaria de fora justamente o trafego que mais interessa contar.

## Por que o identificador vai como hash

Mesma razao do `RefreshToken`: a coluna acumularia e-mails e matriculas
digitados por qualquer um, inclusive erros de digitacao de terceiros, sem que
ninguem precise le-los — o bloqueio e automatico e expira sozinho. O hash
conta igual e nao guarda o dado.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin

#: Marcador para tentativa sem endereco atribuivel (ver `app.core.net`).
#: String em vez de NULL porque em Postgres um NULL nunca e igual a outro, e a
#: restricao de unicidade deixaria de valer exatamente nessas linhas.
IP_DESCONHECIDO = "-"


class LoginAttempt(UUIDPrimaryKeyMixin, Base):
    """Falhas recentes de uma identidade vindas de um endereco.

    Uma linha por par (identidade, endereco). A separacao e o que permite as
    duas leituras que o `login_throttle` faz: somar as linhas de uma identidade
    pega quem insiste na mesma conta trocando de rede, e contar identidades
    distintas de um endereco pega quem testa uma senha contra a empresa toda.
    """

    __tablename__ = "login_attempts"
    __table_args__ = (
        UniqueConstraint("identity_hash", "ip_address", name="uq_login_attempts_identity_ip"),
        Index("ix_login_attempts_identity", "identity_hash", "last_failure_at"),
        Index("ix_login_attempts_ip", "ip_address", "last_failure_at"),
    )

    # SHA-256 de "publico:tenant:identificador".
    identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False, default=IP_DESCONHECIDO)

    failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_failure_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_failure_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return f"<LoginAttempt {self.identity_hash[:8]} x{self.failures}>"
