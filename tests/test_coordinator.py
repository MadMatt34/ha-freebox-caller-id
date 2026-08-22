"""Tests for the Freebox Caller ID coordinator."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest

from custom_components.freebox_caller_id.const import EVENT_INCOMING_CALL
from custom_components.freebox_caller_id.coordinator import FreeboxCallerCoordinator

FREEBOX_HOST = "192.168.1.254"
APP_TOKEN = "test-app-token"
ENTRY_ID = "test-entry-id"
SESSION_TOKEN = "test-session-token"
CHALLENGE = "test-challenge"
FIRMWARE = "4.8.1"
MODEL = "Freebox Ultra"

SYSTEM_INFO = {
    "firmware_version": FIRMWARE,
    "model_info": {
        "pretty_name": MODEL,
    },
}


def _login_responses(aioclient_mock) -> None:
    """Register the Freebox login responses."""
    base_url = f"http://{FREEBOX_HOST}"

    aioclient_mock.get(
        f"{base_url}/api/v4/login/",
        json={
            "result": {
                "challenge": CHALLENGE,
            },
        },
    )

    aioclient_mock.post(
        f"{base_url}/api/v4/login/session/",
        json={
            "success": True,
            "result": {
                "session_token": SESSION_TOKEN,
            },
        },
    )


def _system_response(aioclient_mock) -> None:
    """Register the Freebox system response."""
    aioclient_mock.get(
        f"http://{FREEBOX_HOST}/api/v4/system/",
        json={
            "success": True,
            "result": SYSTEM_INFO,
        },
    )


def _call_log_response(
    aioclient_mock,
    call: dict[str, object] | None,
) -> None:
    """Register the Freebox call-log response."""
    aioclient_mock.get(
        f"http://{FREEBOX_HOST}/api/v4/call/log/",
        json={
            "success": True,
            "result": [] if call is None else [call],
        },
    )


def _call(
    *,
    call_id: int,
    call_type: str,
    duration: int,
    datetime: float = 1_000.0,
    number: str = "0123456789",
    name: str | None = "Test Caller",
) -> dict[str, object]:
    """Build a call-log entry."""
    return {
        "id": call_id,
        "type": call_type,
        "duration": duration,
        "datetime": datetime,
        "number": number,
        "name": name,
    }


def _create_coordinator(
    hass: HomeAssistant,
) -> FreeboxCallerCoordinator:
    """Create a coordinator."""
    return FreeboxCallerCoordinator(
        hass=hass,
        session=async_get_clientsession(hass),
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )


def _set_cached_system_info(
    coordinator: FreeboxCallerCoordinator,
) -> None:
    """Set cached system information for call-log-focused tests."""
    coordinator.system_info = SYSTEM_INFO.copy()


class _Response:
    """Minimal aiohttp response for sequence tests."""

    def __init__(
        self,
        *,
        status: int,
        payload: object,
        json_error: Exception | None = None,
    ) -> None:
        """Initialize the response."""
        self.status = status
        self._payload = payload
        self._json_error = json_error

    async def json(self) -> object:
        """Return the JSON payload."""
        if self._json_error is not None:
            raise self._json_error

        return self._payload

    async def __aenter__(self) -> _Response:
        """Enter the response context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> None:
        """Exit the response context manager."""


class _SequenceSession:
    """Minimal session returning queued responses."""

    def __init__(
        self,
        *,
        call_log_responses: list[_Response] | None = None,
        system_responses: list[_Response] | None = None,
        challenge_response: _Response | None = None,
        session_response: _Response | None = None,
        exception: Exception | None = None,
    ) -> None:
        """Initialize the response queues."""
        self._call_log_responses = call_log_responses or []
        self._system_responses = system_responses or []
        self._challenge_response = challenge_response
        self._session_response = session_response
        self._exception = exception

    @asynccontextmanager
    async def get(
        self,
        url: str,
        **kwargs: Any,
    ) -> AsyncIterator[_Response]:
        """Return the next configured GET response."""
        if self._exception is not None:
            raise self._exception

        if url.endswith("/api/v4/call/log/"):
            if not self._call_log_responses:
                raise AssertionError("No call-log response left")

            yield self._call_log_responses.pop(0)
            return

        if url.endswith("/api/v4/system/"):
            if not self._system_responses:
                raise AssertionError("No system response left")

            yield self._system_responses.pop(0)
            return

        if url.endswith("/api/v4/login/"):
            if self._challenge_response is None:
                raise AssertionError("No challenge response configured")

            yield self._challenge_response
            return

        raise AssertionError(f"Unexpected GET URL: {url}")

    @asynccontextmanager
    async def post(
        self,
        url: str,
        **kwargs: Any,
    ) -> AsyncIterator[_Response]:
        """Return the configured session response."""
        if self._exception is not None:
            raise self._exception

        if not url.endswith("/api/v4/login/session/"):
            raise AssertionError(f"Unexpected POST URL: {url}")

        if self._session_response is None:
            raise AssertionError("No session response configured")

        yield self._session_response


async def test_first_call_initializes_without_event(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test that the first call only initializes the last seen ID."""
    _login_responses(aioclient_mock)
    _system_response(aioclient_mock)
    _call_log_response(
        aioclient_mock,
        _call(
            call_id=1,
            call_type="accepted",
            duration=0,
        ),
    )

    coordinator = _create_coordinator(hass)

    events: list[object] = []
    hass.bus.async_listen(
        EVENT_INCOMING_CALL,
        events.append,
    )

    data = await coordinator._async_update_data()

    assert coordinator._last_seen_call_id == 1
    assert events == []
    assert data["is_ringing"] is True


async def test_new_incoming_call_fires_event(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test that a new incoming call fires an event."""
    _system_response(aioclient_mock)
    _call_log_response(
        aioclient_mock,
        _call(
            call_id=2,
            call_type="missed",
            duration=0,
        ),
    )

    coordinator = _create_coordinator(hass)
    coordinator.session_token = SESSION_TOKEN
    coordinator._last_seen_call_id = 1

    events: list[object] = []
    hass.bus.async_listen(
        EVENT_INCOMING_CALL,
        events.append,
    )

    await coordinator._async_update_data()
    await hass.async_block_till_done()

    assert coordinator._last_seen_call_id == 2
    assert len(events) == 1
    assert events[0].data["id"] == 2
    assert events[0].data["number"] == "0123456789"
    assert events[0].data["name"] == "Test Caller"
    assert events[0].data["type"] == "missed"


async def test_existing_call_does_not_fire_again(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test that an unchanged call ID does not fire another event."""
    _system_response(aioclient_mock)
    _call_log_response(
        aioclient_mock,
        _call(
            call_id=1,
            call_type="missed",
            duration=0,
        ),
    )

    coordinator = _create_coordinator(hass)
    coordinator.session_token = SESSION_TOKEN
    coordinator._last_seen_call_id = 1

    events: list[object] = []
    hass.bus.async_listen(
        EVENT_INCOMING_CALL,
        events.append,
    )

    await coordinator._async_update_data()
    await hass.async_block_till_done()

    assert events == []


async def test_outgoing_call_does_not_fire_event(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test that an outgoing call does not fire an event."""
    _system_response(aioclient_mock)
    _call_log_response(
        aioclient_mock,
        _call(
            call_id=2,
            call_type="outgoing",
            duration=10,
        ),
    )

    coordinator = _create_coordinator(hass)
    coordinator.session_token = SESSION_TOKEN
    coordinator._last_seen_call_id = 1

    events: list[object] = []
    hass.bus.async_listen(
        EVENT_INCOMING_CALL,
        events.append,
    )

    data = await coordinator._async_update_data()
    await hass.async_block_till_done()

    assert coordinator._last_seen_call_id == 2
    assert events == []
    assert data["is_ringing"] is False


async def test_empty_call_log_is_valid(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test that an empty call log is valid."""
    _system_response(aioclient_mock)
    _call_log_response(aioclient_mock, None)

    coordinator = _create_coordinator(hass)
    coordinator.session_token = SESSION_TOKEN

    data = await coordinator._async_update_data()

    assert data == {
        "system": SYSTEM_INFO,
    }


@pytest.mark.parametrize(
    ("call_type", "expected"),
    [
        ("accepted", True),
        ("missed", True),
        ("outgoing", False),
    ],
)
async def test_is_incoming(
    hass: HomeAssistant,
    call_type: str,
    expected: bool,
) -> None:
    """Test incoming call classification."""
    coordinator = _create_coordinator(hass)

    assert coordinator._is_incoming(call_type) is expected


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        (0, True),
        (1, False),
    ],
)
async def test_is_ringing_uses_duration_zero(
    hass: HomeAssistant,
    duration: int,
    expected: bool,
) -> None:
    """Test the duration == 0 ringing criterion."""
    coordinator = _create_coordinator(hass)

    assert (
        coordinator._is_ringing(
            call_type="accepted",
            duration=duration,
            call_time=1_000,
            now=1_010,
        )
        is expected
    )


async def test_is_ringing_expires_after_timeout(
    hass: HomeAssistant,
) -> None:
    """Test that ringing expires after the configured timeout."""
    coordinator = _create_coordinator(hass)

    assert (
        coordinator._is_ringing(
            call_type="accepted",
            duration=0,
            call_time=1_000,
            now=1_044,
        )
        is True
    )

    assert (
        coordinator._is_ringing(
            call_type="accepted",
            duration=0,
            call_time=1_000,
            now=1_045,
        )
        is False
    )


async def test_update_failed_clears_connection_state(
    hass: HomeAssistant,
) -> None:
    """Test that a failed update clears the Freebox connection state."""
    coordinator = _create_coordinator(hass)
    coordinator.session_token = SESSION_TOKEN
    coordinator.system_info = {
        "firmware_version": FIRMWARE,
    }

    device_info = coordinator.device_info

    with pytest.raises(UpdateFailed):
        coordinator._handle_failure("Freebox unavailable")

    assert coordinator.session_token is None
    assert coordinator.system_info == {}
    assert coordinator.device_info is device_info


async def test_invalid_app_token_raises_auth_failed(
    hass: HomeAssistant,
) -> None:
    """Test that an invalid Freebox app token triggers reauthentication."""
    session = _SequenceSession(
        challenge_response=_Response(
            status=200,
            payload={
                "result": {
                    "challenge": CHALLENGE,
                },
            },
        ),
        session_response=_Response(
            status=403,
            payload={
                "success": False,
                "error_code": "invalid_token",
            },
        ),
    )

    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=session,  # type: ignore[arg-type]
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_get_session()


async def test_login_http_error(
    hass: HomeAssistant,
) -> None:
    """Test a non-200 response from the login challenge endpoint."""
    session = _SequenceSession(
        challenge_response=_Response(
            status=500,
            payload={},
        ),
    )

    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=session,  # type: ignore[arg-type]
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )

    assert await coordinator._async_get_session() is False


async def test_login_challenge_json_error(
    hass: HomeAssistant,
) -> None:
    """Test invalid JSON from the login challenge endpoint."""
    session = _SequenceSession(
        challenge_response=_Response(
            status=200,
            payload={},
            json_error=ValueError("invalid json"),
        ),
    )

    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=session,  # type: ignore[arg-type]
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )

    assert await coordinator._async_get_session() is False


@pytest.mark.parametrize(
    ("status", "payload"),
    [
        (401, {}),
        (500, {}),
    ],
)
async def test_session_http_error(
    hass: HomeAssistant,
    status: int,
    payload: dict[str, object],
) -> None:
    """Test non-200 session responses."""
    session = _SequenceSession(
        challenge_response=_Response(
            status=200,
            payload={
                "result": {
                    "challenge": CHALLENGE,
                },
            },
        ),
        session_response=_Response(
            status=status,
            payload=payload,
        ),
    )

    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=session,  # type: ignore[arg-type]
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )

    assert await coordinator._async_get_session() is False


async def test_session_403_invalid_json(
    hass: HomeAssistant,
) -> None:
    """Test a 403 session response containing invalid JSON."""
    session = _SequenceSession(
        challenge_response=_Response(
            status=200,
            payload={
                "result": {
                    "challenge": CHALLENGE,
                },
            },
        ),
        session_response=_Response(
            status=403,
            payload={},
            json_error=ValueError("invalid json"),
        ),
    )

    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=session,  # type: ignore[arg-type]
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )

    assert await coordinator._async_get_session() is False


async def test_session_403_other_error(
    hass: HomeAssistant,
) -> None:
    """Test a 403 session response with another error code."""
    session = _SequenceSession(
        challenge_response=_Response(
            status=200,
            payload={
                "result": {
                    "challenge": CHALLENGE,
                },
            },
        ),
        session_response=_Response(
            status=403,
            payload={
                "success": False,
                "error_code": "auth_required",
            },
        ),
    )

    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=session,  # type: ignore[arg-type]
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )

    assert await coordinator._async_get_session() is False


async def test_session_success_false(
    hass: HomeAssistant,
) -> None:
    """Test an unsuccessful session response."""
    session = _SequenceSession(
        challenge_response=_Response(
            status=200,
            payload={
                "result": {
                    "challenge": CHALLENGE,
                },
            },
        ),
        session_response=_Response(
            status=200,
            payload={
                "success": False,
                "result": {},
            },
        ),
    )

    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=session,  # type: ignore[arg-type]
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )

    assert await coordinator._async_get_session() is False


async def test_system_info_http_error(
    hass: HomeAssistant,
) -> None:
    """Test a non-200 system info response."""
    session = _SequenceSession(
        system_responses=[
            _Response(
                status=500,
                payload={},
            ),
        ],
    )

    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=session,  # type: ignore[arg-type]
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )

    await coordinator._async_fetch_system_info(
        {"X-Fbx-App-Auth": SESSION_TOKEN},
    )

    assert coordinator.system_info == {}


async def test_system_info_unsuccessful_response(
    hass: HomeAssistant,
) -> None:
    """Test an unsuccessful system info response."""
    session = _SequenceSession(
        system_responses=[
            _Response(
                status=200,
                payload={
                    "success": False,
                    "result": {},
                },
            ),
        ],
    )

    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=session,  # type: ignore[arg-type]
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )

    await coordinator._async_fetch_system_info(
        {"X-Fbx-App-Auth": SESSION_TOKEN},
    )

    assert coordinator.system_info == {}


@pytest.mark.parametrize(
    "error",
    [
        aiohttp.ClientError("connection failed"),
        TimeoutError(),
        ValueError("invalid json"),
        KeyError("result"),
        TypeError("invalid type"),
    ],
)
async def test_system_info_errors_are_non_fatal(
    hass: HomeAssistant,
    error: Exception,
) -> None:
    """Test recoverable system information errors."""
    session = _SequenceSession(
        exception=error,
    )

    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=session,  # type: ignore[arg-type]
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )

    await coordinator._async_fetch_system_info(
        {"X-Fbx-App-Auth": SESSION_TOKEN},
    )

    assert coordinator.system_info == {}


async def test_session_expired_is_renewed(
    hass: HomeAssistant,
) -> None:
    """Test that a 403 on the call log causes session renewal."""
    session = _SequenceSession(
        call_log_responses=[
            _Response(
                status=403,
                payload={},
            ),
            _Response(
                status=200,
                payload={
                    "success": True,
                    "result": [],
                },
            ),
        ],
        challenge_response=_Response(
            status=200,
            payload={
                "result": {
                    "challenge": CHALLENGE,
                },
            },
        ),
        session_response=_Response(
            status=200,
            payload={
                "success": True,
                "result": {
                    "session_token": SESSION_TOKEN,
                },
            },
        ),
    )

    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=session,  # type: ignore[arg-type]
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )
    coordinator.session_token = "expired-token"
    _set_cached_system_info(coordinator)

    data = await coordinator._async_update_data()

    assert coordinator.session_token == SESSION_TOKEN
    assert data == {
        "system": SYSTEM_INFO,
    }


async def test_session_renewal_failure(
    hass: HomeAssistant,
) -> None:
    """Test that a failed session renewal makes the coordinator unavailable."""
    session = _SequenceSession(
        call_log_responses=[
            _Response(
                status=403,
                payload={},
            ),
        ],
        challenge_response=_Response(
            status=200,
            payload={
                "result": {
                    "challenge": CHALLENGE,
                },
            },
        ),
        session_response=_Response(
            status=500,
            payload={},
        ),
    )

    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=session,  # type: ignore[arg-type]
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )
    coordinator.session_token = "expired-token"
    _set_cached_system_info(coordinator)

    with pytest.raises(
        UpdateFailed,
        match="Failed to renew the session",
    ):
        await coordinator._async_update_data()


async def test_call_log_retry_failure(
    hass: HomeAssistant,
) -> None:
    """Test that a failed call-log retry raises UpdateFailed."""
    session = _SequenceSession(
        call_log_responses=[
            _Response(
                status=403,
                payload={},
            ),
            _Response(
                status=500,
                payload={},
            ),
        ],
        challenge_response=_Response(
            status=200,
            payload={
                "result": {
                    "challenge": CHALLENGE,
                },
            },
        ),
        session_response=_Response(
            status=200,
            payload={
                "success": True,
                "result": {
                    "session_token": SESSION_TOKEN,
                },
            },
        ),
    )

    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=session,  # type: ignore[arg-type]
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )
    coordinator.session_token = "expired-token"
    _set_cached_system_info(coordinator)

    with pytest.raises(
        UpdateFailed,
        match="HTTP error 500",
    ):
        await coordinator._async_update_data()


async def test_call_log_http_error(
    hass: HomeAssistant,
) -> None:
    """Test a non-200 call-log response."""
    session = _SequenceSession(
        call_log_responses=[
            _Response(
                status=500,
                payload={},
            ),
        ],
    )

    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=session,  # type: ignore[arg-type]
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )
    coordinator.session_token = SESSION_TOKEN
    _set_cached_system_info(coordinator)

    with pytest.raises(
        UpdateFailed,
        match="HTTP error 500",
    ):
        await coordinator._async_update_data()


async def test_call_log_unsuccessful_response(
    hass: HomeAssistant,
) -> None:
    """Test an unsuccessful call-log response."""
    session = _SequenceSession(
        call_log_responses=[
            _Response(
                status=200,
                payload={
                    "success": False,
                    "result": [],
                },
            ),
        ],
    )

    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=session,  # type: ignore[arg-type]
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )
    coordinator.session_token = SESSION_TOKEN
    _set_cached_system_info(coordinator)

    with pytest.raises(
        UpdateFailed,
        match="Invalid API response",
    ):
        await coordinator._async_update_data()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", "invalid", "Invalid Freebox call ID"),
        ("type", "invalid", "Invalid Freebox call type"),
        ("duration", "invalid", "Invalid Freebox call duration"),
        ("datetime", "invalid", "Invalid Freebox call timestamp"),
    ],
)
async def test_invalid_call_data(
    hass: HomeAssistant,
    field: str,
    value: object,
    message: str,
) -> None:
    """Test validation of the latest call data."""
    call = _call(
        call_id=1,
        call_type="accepted",
        duration=0,
    )
    call[field] = value

    session = _SequenceSession(
        call_log_responses=[
            _Response(
                status=200,
                payload={
                    "success": True,
                    "result": [call],
                },
            ),
        ],
    )

    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=session,  # type: ignore[arg-type]
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )
    coordinator.session_token = SESSION_TOKEN
    _set_cached_system_info(coordinator)

    with pytest.raises(
        UpdateFailed,
        match=message,
    ):
        await coordinator._async_update_data()


async def test_recent_calls_ignore_invalid_entries(
    hass: HomeAssistant,
) -> None:
    """Test invalid recent calls are ignored."""
    valid_call = _call(
        call_id=1,
        call_type="accepted",
        duration=10,
    )

    invalid_id = _call(
        call_id=2,
        call_type="accepted",
        duration=10,
    )
    invalid_id["id"] = "invalid"

    invalid_type = _call(
        call_id=3,
        call_type="accepted",
        duration=10,
    )
    invalid_type["type"] = "invalid"

    invalid_duration = _call(
        call_id=4,
        call_type="accepted",
        duration=10,
    )
    invalid_duration["duration"] = "invalid"

    invalid_timestamp = _call(
        call_id=5,
        call_type="accepted",
        duration=10,
    )
    invalid_timestamp["datetime"] = "invalid"

    session = _SequenceSession(
        call_log_responses=[
            _Response(
                status=200,
                payload={
                    "success": True,
                    "result": [
                        valid_call,
                        invalid_id,
                        invalid_type,
                        invalid_duration,
                        invalid_timestamp,
                    ],
                },
            ),
        ],
    )

    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=session,  # type: ignore[arg-type]
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )
    coordinator.session_token = SESSION_TOKEN
    _set_cached_system_info(coordinator)

    data = await coordinator._async_update_data()

    assert data["recent_calls"] == [
        {
            "id": 1,
            "number": "0123456789",
            "name": "Test Caller",
            "type": "accepted",
            "duration": 10,
            "timestamp": 1_000.0,
        },
    ]


async def test_unexpected_error_is_converted_to_update_failed(
    hass: HomeAssistant,
) -> None:
    """Test unexpected exceptions are converted to UpdateFailed."""

    class BrokenSession:
        """Session raising an unexpected exception."""

        @asynccontextmanager
        async def get(
            self,
            url: str,
            **kwargs: Any,
        ) -> AsyncIterator[_Response]:
            """Raise an unexpected exception."""
            raise RuntimeError("unexpected failure")
            yield

        @asynccontextmanager
        async def post(
            self,
            url: str,
            **kwargs: Any,
        ) -> AsyncIterator[_Response]:
            """Raise an unexpected exception."""
            raise RuntimeError("unexpected failure")
            yield

    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=BrokenSession(),  # type: ignore[arg-type]
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )

    with pytest.raises(
        UpdateFailed,
        match="Unexpected error: unexpected failure",
    ):
        await coordinator._async_update_data()


async def test_device_info_falls_back_to_board_name(
    hass: HomeAssistant,
) -> None:
    """Test DeviceInfo fallback to board_name."""
    coordinator = _create_coordinator(hass)

    coordinator.system_info = {
        "board_name": "fbxserver",
    }

    coordinator._update_device_info()

    assert coordinator.device_info["model"] == ("Freebox Server (modèle fbxserver)")


async def test_system_info_is_cached(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test that system information is not fetched on every update."""
    _login_responses(aioclient_mock)
    _system_response(aioclient_mock)
    _call_log_response(
        aioclient_mock,
        None,
    )

    coordinator = _create_coordinator(hass)
    coordinator.session_token = SESSION_TOKEN

    await coordinator._async_update_data()

    _call_log_response(
        aioclient_mock,
        None,
    )

    await coordinator._async_update_data()

    # The system endpoint was registered once and system_info is cached,
    # so the second update only consumes a call-log response.
    assert coordinator.system_info == SYSTEM_INFO
