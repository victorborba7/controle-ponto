"""Enumeracoes do dominio.

Todas herdam de str para serializarem direto em JSON e serem persistidas
como texto legivel no banco (facilita inspecao manual e relatorio do RH).
"""

from enum import StrEnum


class UserRole(StrEnum):
    """Papel de quem acessa o painel administrativo."""

    OWNER = "owner"
    HR = "hr"
    VIEWER = "viewer"


class EmployeeStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class DevicePlatform(StrEnum):
    ANDROID = "android"
    IOS = "ios"


class EntryType(StrEnum):
    """Tipo de batida. O MVP usa IN/OUT; os intervalos ja ficam previstos."""

    IN = "in"
    OUT = "out"
    BREAK_START = "break_start"
    BREAK_END = "break_end"


class LocationMethod(StrEnum):
    """Qual elo da cadeia de fallback validou a presenca.

    Requisito explicito do projeto: todo ponto guarda como a presenca foi
    confirmada, para auditoria e para pesar a confianca do registro depois.
    """

    BEACON = "beacon"
    WIFI = "wifi"
    GPS = "gps"
    NONE = "none"


class BeaconProtocol(StrEnum):
    """Protocolo do advertisement.

    Os dois formatos convivem de proposito: a escolha do hardware ainda esta
    em aberto por causa do risco R1 (iOS nao entrega advertisement de iBeacon
    via CoreBluetooth), e o backend nao pode ficar refem dessa decisao.
    """

    IBEACON = "ibeacon"
    EDDYSTONE = "eddystone"


class TimeEntryStatus(StrEnum):
    """Desfecho da validacao do ponto.

    PENDING_REVIEW existe porque bloquear o funcionario de bater ponto e pior
    que gerar um registro para o RH conferir (decisao D5).
    """

    APPROVED = "approved"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"


class ConsentType(StrEnum):
    """Tipos de consentimento LGPD coletados separadamente."""

    BIOMETRIC = "biometric"
    LOCATION = "location"


class AuditAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    TIME_ENTRY = "time_entry"
    REVIEW = "review"
    CONSENT_GRANTED = "consent_granted"
    CONSENT_REVOKED = "consent_revoked"
