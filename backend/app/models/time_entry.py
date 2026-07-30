"""TimeEntry — o registro de ponto. Tabela central do produto.

Guarda nao so "fulano bateu ponto as 8h", mas *como* isso foi comprovado:
score do rosto, resultado do liveness e qual elo da cadeia de localizacao
validou a presenca. E o que permite auditar um registro meses depois.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import EntryType, LocationMethod, TimeEntryStatus


class TimeEntry(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "time_entries"
    __table_args__ = (
        # Consulta dominante do painel: pontos de um funcionario num periodo.
        Index("ix_time_entries_tenant_employee_time", "tenant_id", "employee_id", "recorded_at"),
        # Fila de revisao do RH.
        Index("ix_time_entries_tenant_status", "tenant_id", "status"),
        # Relatorio por periodo do tenant inteiro.
        Index("ix_time_entries_tenant_time", "tenant_id", "recorded_at"),
        # Protecao contra batida duplicada: o app manda uma chave por tentativa,
        # e o retry de uma rede instavel no hangar nao vira dois registros.
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_time_entries_idempotency"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
    )

    entry_type: Mapped[EntryType] = mapped_column(
        Enum(EntryType, name="entry_type", native_enum=False, length=20),
        nullable=False,
    )

    # Horario do servidor: e o que vale juridicamente. O relogio do celular e
    # ajustavel pelo proprio funcionario.
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Horario que o aparelho reportou. Guardado so para detectar divergencia
    # (envio offline atrasado ou relogio adulterado).
    client_recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Evidencia facial ---
    face_match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_face_template_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("face_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    liveness_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    liveness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Selfie do momento da batida. Expira pela politica de retencao (Etapa 11);
    # quando expurgada, a chave vira nula e o registro permanece.
    selfie_image_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # --- Evidencia de localizacao ---
    # Requisito explicito do projeto: todo ponto guarda qual metodo validou.
    location_method: Mapped[LocationMethod] = mapped_column(
        Enum(LocationMethod, name="location_method", native_enum=False, length=20),
        nullable=False,
        default=LocationMethod.NONE,
    )
    location_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    site_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True
    )
    beacon_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("beacons.id", ondelete="SET NULL"), nullable=True
    )
    wifi_network_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("wifi_networks.id", ondelete="SET NULL"), nullable=True
    )

    beacon_rssi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_to_site_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Payload cru de localizacao que o app enviou (todos os beacons vistos,
    # redes, GPS). Preservado para auditoria e para reavaliar um registro
    # contestado com a regra que valia na epoca.
    # JSONB no Postgres, JSON no resto (o SQLite dos testes nao tem JSONB).
    location_raw: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )

    # --- Desfecho ---
    status: Mapped[TimeEntryStatus] = mapped_column(
        Enum(TimeEntryStatus, name="time_entry_status", native_enum=False, length=20),
        nullable=False,
        default=TimeEntryStatus.PENDING_REVIEW,
    )
    # Por que caiu em revisao ou foi rejeitado, em texto legivel pelo RH.
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    idempotency_key: Mapped[str | None] = mapped_column(String(80), nullable=True)

    def __repr__(self) -> str:
        return f"<TimeEntry {self.entry_type} {self.recorded_at} via {self.location_method}>"
