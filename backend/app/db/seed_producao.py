"""Cria o primeiro tenant de um ambiente de producao.

    fly ssh console --app waypoint-api -C "python -m app.db.seed_producao"

Diferente do `seed.py`, que povoa desenvolvimento com gente ficticia e
coordenadas de exemplo. Aqui nada e inventado: tudo vem de variavel de
ambiente, porque dado de cliente nao pode ficar versionado no repositorio e
porque cada ambiente tem os seus.

Idempotente pelo slug do tenant: rodar duas vezes nao duplica nada.

**A senha do admin e sorteada e impressa uma unica vez.** Nao ha como
recupera-la depois — o banco guarda so o hash Argon2. Copie da saida antes de
fechar o terminal.

Variaveis (as marcadas com * nao tem padrao e o script recusa rodar sem elas):

    SEED_TENANT_NAME      nome da empresa
    SEED_TENANT_SLUG      identificador curto, minusculo
    SEED_ADMIN_EMAIL   *  login do admin do RH
    SEED_ADMIN_NAME       nome exibido do admin
    SEED_SITE_NAME        nome do local
    SEED_SITE_ADDRESS     endereco, para leitura humana
    SEED_SITE_LAT      *  latitude, em graus decimais
    SEED_SITE_LNG      *  longitude, em graus decimais
    SEED_SITE_RADIUS_M    raio do geofence em metros
    SEED_TIMEZONE         fuso IANA (ex.: America/New_York)
    SEED_EMPLOYEE_CODE    matricula do funcionario de teste; vazio = nao cria
    SEED_EMPLOYEE_NAME    nome do funcionario de teste

Lat/lng nao tem padrao de proposito. Coordenada aproximada com raio de 100 m
significa funcionario parado na porta sem conseguir bater ponto, e a falha nao
se parece com erro de configuracao: parece o sistema funcionando e recusando
alguem que esta no lugar certo. Melhor recusar a rodar.
"""

import asyncio
import os
import secrets
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models import (
    Employee,
    EmployeeStatus,
    Site,
    Tenant,
    User,
    UserRole,
)


class ConfigAusente(RuntimeError):
    pass


def _texto(nome: str, padrao: str | None = None) -> str:
    valor = os.environ.get(nome, padrao if padrao is not None else "").strip()
    if not valor:
        raise ConfigAusente(f"{nome} e obrigatoria e veio vazia.")
    return valor


def _coordenada(nome: str, minimo: float, maximo: float) -> float:
    bruto = os.environ.get(nome, "").strip()
    if not bruto:
        raise ConfigAusente(
            f"{nome} e obrigatoria. Pegue a coordenada exata no Google Maps: "
            "clique com o botao direito sobre o ponto e copie o par que aparece "
            "no topo do menu."
        )
    try:
        valor = float(bruto.replace(",", "."))
    except ValueError as exc:
        raise ConfigAusente(f"{nome} nao e um numero: {bruto!r}") from exc
    if not minimo <= valor <= maximo:
        raise ConfigAusente(f"{nome} fora da faixa valida ({minimo}..{maximo}): {valor}")
    return valor


def _fuso(nome: str, padrao: str) -> str:
    valor = os.environ.get(nome, padrao).strip() or padrao
    try:
        ZoneInfo(valor)
    except ZoneInfoNotFoundError as exc:
        raise ConfigAusente(
            f"{nome}={valor!r} nao e um fuso IANA valido (ex.: America/New_York)."
        ) from exc
    return valor


async def semear(session: AsyncSession) -> None:
    slug = _texto("SEED_TENANT_SLUG", "empresa-demo")

    if await session.scalar(select(Tenant).where(Tenant.slug == slug)):
        print(f"Tenant '{slug}' ja existe — nada a fazer.")
        return

    fuso = _fuso("SEED_TIMEZONE", "America/New_York")
    latitude = _coordenada("SEED_SITE_LAT", -90, 90)
    longitude = _coordenada("SEED_SITE_LNG", -180, 180)
    email_admin = _texto("SEED_ADMIN_EMAIL")

    tenant = Tenant(
        name=_texto("SEED_TENANT_NAME", "Empresa Demo"),
        slug=slug,
        timezone=fuso,
    )
    session.add(tenant)
    await session.flush()  # atribui tenant.id para as FKs abaixo

    # Sorteada, nunca fixa: senha padrao em producao e senha que sobrevive ao
    # primeiro acesso e vira porta aberta. Impressa uma vez, so aqui.
    senha_admin = secrets.token_urlsafe(12)
    admin = User(
        tenant_id=tenant.id,
        email=email_admin,
        password_hash=hash_password(senha_admin),
        name=_texto("SEED_ADMIN_NAME", "Administrador"),
        role=UserRole.OWNER,
    )
    session.add(admin)

    site = Site(
        tenant_id=tenant.id,
        name=_texto("SEED_SITE_NAME", "Hangar"),
        address=_texto("SEED_SITE_ADDRESS", "-"),
        latitude=latitude,
        longitude=longitude,
        geofence_radius_m=int(os.environ.get("SEED_SITE_RADIUS_M", "100")),
        timezone=fuso,
    )
    session.add(site)
    await session.flush()

    # Beacons e redes Wi-Fi NAO entram aqui: dependem do mapeamento fisico do
    # local e sao cadastrados pelo painel, onde o RH ve o que esta fazendo.
    # Semear identificador inventado criaria um beacon que nunca casa, e a
    # falha e silenciosa (Etapa 5).

    matricula = os.environ.get("SEED_EMPLOYEE_CODE", "").strip()
    senha_funcionario: str | None = None
    if matricula:
        senha_funcionario = secrets.token_urlsafe(9)
        session.add(
            Employee(
                tenant_id=tenant.id,
                external_code=matricula,
                name=_texto("SEED_EMPLOYEE_NAME", "Funcionario de Teste"),
                password_hash=hash_password(senha_funcionario),
                status=EmployeeStatus.ACTIVE,
                default_site_id=site.id,
            )
        )

    await session.commit()

    print("Seed de producao concluido.\n")
    print(f"  tenant .......: {tenant.name}  (slug: {tenant.slug})")
    print(f"  fuso .........: {fuso}")
    print(f"  site .........: {site.name} — {site.address}")
    print(f"  geofence .....: {latitude}, {longitude} · raio {site.geofence_radius_m} m")
    print("\n  ADMIN DO PAINEL")
    print(f"    email ......: {admin.email}")
    print(f"    senha ......: {senha_admin}")
    if senha_funcionario:
        print("\n  FUNCIONARIO (app)")
        print(f"    matricula ..: {matricula}")
        print(f"    senha ......: {senha_funcionario}")
    print("\n  As senhas acima nao serao exibidas de novo. Guarde agora.")


async def main() -> None:
    try:
        async with AsyncSessionLocal() as session:
            await semear(session)
    except ConfigAusente as exc:
        print(f"\nConfiguracao incompleta: {exc}\n", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    asyncio.run(main())
