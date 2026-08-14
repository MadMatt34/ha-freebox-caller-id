"""Types utilisés par l'intégration Freebox Caller ID."""

from __future__ import annotations

from typing import Literal, TypedDict


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


class FreeboxLoginResult(TypedDict):
    """Résultat de l'authentification initiale Freebox."""

    challenge: str


class FreeboxSessionResult(TypedDict):
    """Résultat de l'ouverture d'une session Freebox."""

    session_token: str


class FreeboxLoginResponse(TypedDict, total=False):
    """Réponse de l'API Freebox lors de l'authentification."""

    success: bool
    result: FreeboxLoginResult | FreeboxSessionResult


class FreeboxSystemResponse(TypedDict, total=False):
    """Réponse de l'API Freebox pour les informations système."""

    success: bool
    result: FreeboxSystemInfo


class FreeboxCallLogResponse(TypedDict, total=False):
    """Réponse de l'API Freebox pour le journal d'appels."""

    success: bool
    result: list[FreeboxCall]
