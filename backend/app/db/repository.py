"""Repositorio com escopo de tenant.

Toda leitura e escrita de dado de negocio passa por aqui. O objetivo e que
esquecer o filtro de tenant seja *impossivel por construcao*, e nao uma regra
que cada desenvolvedor precisa lembrar em cada consulta — que e exatamente
como vazamento entre clientes acontece na pratica.

Uso:

    repo = TenantRepository(session, principal.tenant_id)
    funcionarios = await repo.list(Employee)
    funcionario = await repo.get(Employee, employee_id)   # None se for de outro tenant
"""

import uuid
from typing import TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class TenantRepository:
    """Acesso a dados restrito a um unico tenant.

    O tenant_id vem do Principal (portanto do JWT assinado) e e fixado na
    construcao. Nenhum metodo aceita tenant como parametro, justamente para
    que nao exista caminho onde ele venha do cliente.
    """

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def query(self, model: type[ModelT]) -> Select:
        """SELECT do modelo ja filtrado pelo tenant.

        Ponto de partida para consultas mais elaboradas: encadeie `.where()`,
        `.order_by()` etc. que o filtro de tenant permanece.
        """
        return select(model).where(model.tenant_id == self.tenant_id)

    async def get(self, model: type[ModelT], entity_id: uuid.UUID) -> ModelT | None:
        """Busca por id dentro do tenant.

        Registro existente que pertenca a outra empresa retorna None, igual a
        um id inexistente. A indistincao e intencional: responder 404 em vez de
        403 evita confirmar que aquele id existe em algum lugar.
        """
        result = await self.session.execute(
            self.query(model).where(model.id == entity_id).limit(1)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        model: type[ModelT],
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ModelT]:
        result = await self.session.execute(self.query(model).limit(limit).offset(offset))
        return list(result.scalars().all())

    async def count(self, model: type[ModelT]) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(model).where(model.tenant_id == self.tenant_id)
        )
        return result.scalar_one()

    def add(self, entity: ModelT) -> ModelT:
        """Persiste marcando o tenant do repositorio.

        Sobrescreve qualquer tenant_id que venha preenchido: se um payload
        conseguisse ditar o tenant do registro, todo o isolamento cairia.
        """
        entity.tenant_id = self.tenant_id
        self.session.add(entity)
        return entity

    async def flush(self) -> None:
        await self.session.flush()
