"""Modelos do dominio.

Este modulo importa todos os modelos para que fiquem registrados no metadata
da Base — e o que permite ao Alembic enxergar o schema completo no autogenerate.
Ao criar um modelo novo, adicione-o aqui.
"""

from app.db.base import Base
from app.models.compliance import AuditLog, Consent
from app.models.employee import Device, Employee
from app.models.enums import (
    AuditAction,
    BeaconProtocol,
    ConsentType,
    DevicePlatform,
    EmployeeStatus,
    EntryType,
    LabelMode,
    LocationMethod,
    NoteMode,
    SubjectType,
    TimeEntryStatus,
    UserRole,
)
from app.models.face_template import EMBEDDING_DIM, FaceTemplate
from app.models.location import Beacon, Site, WifiNetwork
from app.models.login_attempt import IP_DESCONHECIDO, LoginAttempt
from app.models.punch_config import (
    LABEL_MAX_LENGTH,
    NOTE_MAX_LENGTH,
    PunchConfig,
    PunchLabel,
)
from app.models.refresh_token import RefreshToken
from app.models.reminder import PunchReminder
from app.models.tenant import Tenant
from app.models.time_entry import TimeEntry
from app.models.user import User

__all__ = [
    "EMBEDDING_DIM",
    "IP_DESCONHECIDO",
    "LABEL_MAX_LENGTH",
    "NOTE_MAX_LENGTH",
    "AuditAction",
    "AuditLog",
    "Base",
    "Beacon",
    "BeaconProtocol",
    "Consent",
    "ConsentType",
    "Device",
    "DevicePlatform",
    "Employee",
    "EmployeeStatus",
    "EntryType",
    "FaceTemplate",
    "LabelMode",
    "LocationMethod",
    "LoginAttempt",
    "NoteMode",
    "PunchConfig",
    "PunchLabel",
    "PunchReminder",
    "RefreshToken",
    "Site",
    "SubjectType",
    "Tenant",
    "TimeEntry",
    "TimeEntryStatus",
    "User",
    "UserRole",
    "WifiNetwork",
]
