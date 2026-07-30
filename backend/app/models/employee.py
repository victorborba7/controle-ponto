"""Employee — o funcionario que bate ponto, e o dispositivo pareado a ele."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import enum_column
from app.models.enums import DevicePlatform, EmployeeStatus


class Employee(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_code", name="uq_employees_tenant_code"),
        UniqueConstraint("tenant_id", "cpf", name="uq_employees_tenant_cpf"),
    )

    # Matricula da empresa. E por ela que o funcionario faz login no app —
    # nem todo operario de hangar tem email corporativo.
    external_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    cpf: Mapped[str | None] = mapped_column(String(14), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Credencial do app. Fica aqui, e nao em tabela separada, porque e 1:1 e
    # sempre carregada junto no login.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[EmployeeStatus] = mapped_column(
        enum_column(EmployeeStatus, "employee_status", length=20),
        nullable=False,
        default=EmployeeStatus.ACTIVE,
    )
    hired_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    terminated_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Site padrao onde este funcionario trabalha (opcional: quem circula entre
    # unidades fica sem, e a validacao aceita qualquer site do tenant).
    default_site_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
    )

    devices: Mapped[list["Device"]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Employee {self.external_code} {self.name}>"


class Device(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Aparelho pareado a um funcionario.

    Existe para amarrar o ponto a um celular conhecido: sem isso, credencial
    vazada bate ponto de qualquer lugar. Um funcionario pode ter mais de um
    device ativo (trocou de aparelho), mas cada batida registra qual usou.
    """

    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "device_fingerprint", name="uq_devices_tenant_fingerprint"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Identificador estavel gerado pelo app e guardado no secure storage.
    device_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[DevicePlatform] = mapped_column(
        enum_column(DevicePlatform, "device_platform", length=20),
        nullable=False,
    )
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    os_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    push_token: Mapped[str | None] = mapped_column(String(500), nullable=True)

    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Revogacao em vez de delete: o historico de pontos aponta para o device.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    employee: Mapped["Employee"] = relationship(back_populates="devices")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def __repr__(self) -> str:
        return f"<Device {self.platform} {self.device_fingerprint[:12]}>"
