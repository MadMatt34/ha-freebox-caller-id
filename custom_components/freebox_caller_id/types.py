"""Types for the Freebox Caller ID integration."""

from __future__ import annotations

from typing import Literal, TypedDict

CallType = Literal["accepted", "missed", "outgoing"]


class FreeboxCall(TypedDict, total=False):
    """Call as returned by the Freebox API."""

    id: int
    number: str | None
    name: str | None
    type: CallType
    duration: int
    datetime: float


class FreeboxRecentCall(TypedDict):
    """Call formatted for the recent calls exposed by the integration."""

    id: int
    number: str | None
    name: str
    type: CallType
    duration: int
    timestamp: float


class FreeboxModelInfo(TypedDict, total=False):
    """Freebox model information."""

    pretty_name: str
    name: str


class FreeboxSystemInfo(TypedDict, total=False):
    """System information returned by the Freebox."""

    firmware_version: str
    model_info: FreeboxModelInfo | str
    board_name: str


class FreeboxCallerData(TypedDict, total=False):
    """Data exposed by the coordinator."""

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
    """Incoming call event data."""

    id: int
    number: str | None
    name: str
    type: CallType
    datetime: float


class FreeboxChallengeResult(TypedDict):
    """Result of the Freebox challenge request."""

    challenge: str


class FreeboxSessionResult(TypedDict):
    """Result of opening a Freebox session."""

    session_token: str


class FreeboxLoginResponse(TypedDict):
    """Freebox response for challenge retrieval."""

    result: FreeboxChallengeResult


class FreeboxErrorResponse(TypedDict, total=False):
    """Generic Freebox API error response."""

    success: bool
    error_code: str
    msg: str
    uid: str


class FreeboxSessionResponse(TypedDict):
    """Freebox response for opening a Freebox session."""

    success: bool
    result: FreeboxSessionResult


class FreeboxSystemResponse(TypedDict):
    """Freebox response for system information."""

    success: bool
    result: FreeboxSystemInfo


class FreeboxCallLogResponse(TypedDict):
    """Freebox response for the call log."""

    success: bool
    result: list[FreeboxCall]


class FreeboxConfigData(TypedDict, total=False):
    """Data persisted in the config entry."""

    host: str
    app_token: str
    scan_interval: int


class FreeboxOptionsData(TypedDict, total=False):
    """Configurable integration options."""

    scan_interval: int
    ringing_timeout: int


class FreeboxUserInput(TypedDict):
    """Data entered during the first config flow step."""

    host: str


class FreeboxAuthorizeResult(TypedDict):
    """Result of a Freebox authorization request."""

    app_token: str
    track_id: str


class FreeboxAuthorizeResponse(TypedDict):
    """Freebox response for an authorization request."""

    success: bool
    result: FreeboxAuthorizeResult


class FreeboxAuthorizationStatusResult(TypedDict):
    """Authorization request status."""

    status: str


class FreeboxAuthorizationStatusResponse(TypedDict):
    """Freebox authorization status response."""

    result: FreeboxAuthorizationStatusResult
