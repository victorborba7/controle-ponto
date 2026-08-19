"""Define a senha de um usuario do painel, por linha de comando.

    fly ssh console --app waypoint-api
    ADMIN_TENANT_SLUG=empresa-demo ADMIN_EMAIL=voce@exemplo.com \
      python -m app.db.trocar_senha_admin

Existe porque o painel ainda nao tem troca de senha para o proprio usuario: a
API expoe `reset_password` para o RH redefinir a senha de um *funcionario*, e
nada equivalente para quem administra. Enquanto essa tela nao existir, este e o
caminho — e tambem o unico jeito de recuperar acesso se a senha sorteada pelo
seed for perdida, porque o banco guarda apenas o hash Argon2.

**A senha e digitada, nunca passada por variavel de ambiente.** Variavel fica no
historico do shell, aparece em `ps` enquanto o processo roda e vaza para
qualquer log que despeje o ambiente. O `getpass` nao ecoa e nao deixa rastro.

Trocar a senha **revoga as sessoes ativas** do usuario. Se a troca foi motivada
por suspeita de vazamento, deixar refresh tokens antigos validos anularia o
proposito: o refresh token vive 30 dias e nao depende da senha para renovar o
acesso.
"""

import asyncio
import getpass
import os
import sys
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models import RefreshToken, Tenant, User
from app.models.enums import SubjectType

TAMANHO_MINIMO = 12


async def trocar(session: AsyncSession) -> int:
    slug = os.environ.get("ADMIN_TENANT_SLUG", "").strip()
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    if not slug or not email:
        print(
            "Defina ADMIN_TENANT_SLUG e ADMIN_EMAIL.\n"
            "  Ex.: ADMIN_TENANT_SLUG=empresa-demo ADMIN_EMAIL=voce@exemplo.com",
            file=sys.stderr,
        )
        return 2

    tenant = await session.scalar(select(Tenant).where(Tenant.slug == slug))
    if tenant is None:
        print(f"Tenant '{slug}' nao existe.", file=sys.stderr)
        return 1

    usuario = await session.scalar(
        select(User).where(User.tenant_id == tenant.id, User.email == email)
    )
    if usuario is None:
        print(f"Nenhum usuario '{email}' no tenant '{slug}'.", file=sys.stderr)
        return 1

    print(f"Trocando a senha de {usuario.name} <{usuario.email}> em {tenant.name}.")

    nova = getpass.getpass("Nova senha: ")
    if len(nova) < TAMANHO_MINIMO:
        print(f"Senha curta demais (minimo {TAMANHO_MINIMO}).", file=sys.stderr)
        return 1
    if nova != getpass.getpass("Repita: "):
        print("As senhas nao conferem.", file=sys.stderr)
        return 1

    usuario.password_hash = hash_password(nova)

    agora = datetime.now(UTC)
    revogados = await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.subject_type == SubjectType.USER,
            RefreshToken.subject_id == usuario.id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=agora)
    )

    await session.commit()

    print("\nSenha alterada.")
    print(f"  sessoes encerradas: {revogados.rowcount}")
    return 0


async def main() -> None:
    async with AsyncSessionLocal() as session:
        raise SystemExit(await trocar(session))


if __name__ == "__main__":
    asyncio.run(main())
