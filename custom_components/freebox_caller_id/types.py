"""Types utilisés par l'intégration Freebox Caller ID."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict


CallType = Literal["accepted", "missed", "outgoing"]


class FreeboxCall(TypedDict, total=False):
    """Appel tel que retourné par l'API Freebox."""

    id: int
    number: str | None
    name: str | None
    type: CallType
    duration: int
    datetime: float


class FreeboxRecentCall(TypedDict):
    """Appel formaté pour l'historique exposé par l'intégration."""

    id: int
    number: str | None
    name: str
    type: CallType
    duration: int
    timestamp: float


class FreeboxModelInfo(TypedDict, total=False):
    """Informations sur le modèle de la Freebox."""

    pretty_name: str
    name: str


class FreeboxSystemInfo(TypedDict, total=False):
    """Informations système retournées par la Freebox."""

    firmware_version: str
    model_info: FreeboxModelInfo | str
    board_name: str


class FreeboxCallerData(TypedDict, total=False):
    """Données exposées par le coordinator."""

    is_ringing: bool
    caller_name: str
    caller_number: str | None
    call_type: CallType
    duration: int
    datetime: float
    id: int
    recent_calls: list[FreeboxRecentCall]
    system: FreeboxSystemInfo


class FreeboxIncomingCallEvent(TypedDict):
    """Données de l'événement d'appel entrant."""

    id: int
    number: str | None
    name: str
    type: CallType
    datetime: float


class FreeboxChallengeResult(TypedDict):
    """Résultat de la demande de challenge Freebox."""

    challenge: str


class FreeboxSessionResult(TypedDict):
    """Résultat de l'ouverture d'une session Freebox."""

    session_token: str


class FreeboxLoginResponse(TypedDict):
    """Réponse Freebox pour la récupération du challenge."""

    result: FreeboxChallengeResult


class FreeboxSessionResponse(TypedDict):
    """Réponse Freebox pour l'ouverture d'une session."""

    success: bool
    result: FreeboxSessionResult


class FreeboxSystemResponse(TypedDict):
    """Réponse de l'API Freebox pour les informations système."""

    success: bool
    result: FreeboxSystemInfo


class FreeboxCallLogResponse(TypedDict):
    """Réponse de l'API Freebox pour le journal d'appels."""

    success: bool
    result: list[FreeboxCall]


class FreeboxConfigData(TypedDict, total=False):
    """Données persistées dans la config entry."""

    host: str
    app_token: str
    scan_interval: int
    area: NotRequired[str]


class FreeboxOptionsData(TypedDict, total=False):
    """Options configurables de l'intégration."""

    scan_interval: int
    ringing_timeout: int


class FreeboxUserInput(TypedDict):
    """Données saisies lors de la première étape du config flow."""

    host: str
    area: str

class FreeboxAuthorizeResult(TypedDict):
    """Résultat de la demande d'autorisation Freebox."""

    app_token: str
    track_id: str


class FreeboxAuthorizeResponse(TypedDict):
    """Réponse de l'API Freebox pour une demande d'autorisation."""

    success: bool
    result: FreeboxAuthorizeResult


class FreeboxAuthorizationStatusResult(TypedDict):
    """Statut d'une demande d'autorisation."""

    status: str


class FreeboxAuthorizationStatusResponse(TypedDict):
    """Réponse du statut d'autorisation Freebox."""

    result: FreeboxAuthorizationStatusResult
