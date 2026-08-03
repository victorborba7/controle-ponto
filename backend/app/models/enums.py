"""Enumeracoes do dominio.

Todas herdam de str para serializarem direto em JSON e serem persistidas
como texto legivel no banco (facilita inspecao manual e relatorio do RH).
"""

from enum import StrEnum


class SubjectType(StrEnum):
    """Quem esta autenticado.

    Os dois publicos vivem em tabelas diferentes (users x employees) e tem
    permissoes disjuntas: admin opera o painel, funcionario bate ponto.
    """

    USER = "user"
    EMPLOYEE = "employee"


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


class NoteMode(StrEnum):
    """Se o funcionario escreve uma observacao ao bater o ponto.

    Existe porque empresas diferentes querem coisas diferentes do mesmo gesto:
    uma quer justificativa de atraso, outra quer o numero da ordem de servico,
    e a maioria nao quer campo nenhum atrapalhando quem so quer bater e entrar.
    """

    HIDDEN = "hidden"
    OPTIONAL = "optional"
    REQUIRED = "required"


class LabelMode(StrEnum):
    """Como o funcionario nomeia a batida, alem do tipo entrada/saida.

    - HIDDEN: so entrada e saida, deduzidas. E o comportamento historico.
    - FREE: o funcionario digita um nome. O tipo continua sendo deduzido — o
      texto descreve, nao decide.
    - LIST: o funcionario escolhe entre opcoes que o RH cadastrou, e **cada
      opcao carrega o tipo**. E o unico modo em que a escolha do funcionario
      muda a contagem de horas, e por isso o unico em que o RH controla as
      alternativas.
    """

    HIDDEN = "hidden"
    FREE = "free"
    LIST = "list"


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
    """Como o beacon e identificado no advertisement.

    Tres modos convivem de proposito, porque a escolha do hardware nao pode
    travar o backend:

    - EDDYSTONE: namespace + instance. Legivel em Android e iOS — o formato
      preferido (decisao D8).
    - IBEACON: uuid + major + minor. Legivel no Android; no iOS so via
      CoreLocation, com o uuid conhecido de antemao.
    - MAC: o endereco do radio. Ultimo recurso, para beacons que transmitem
      formato proprietario que nao sabemos interpretar. **Impossivel no iOS**,
      que nao expoe MAC de periferico por API nenhuma.
    """

    IBEACON = "ibeacon"
    EDDYSTONE = "eddystone"
    MAC = "mac"


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
