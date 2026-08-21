"""Tests for the Freebox Caller ID coordinator."""

from __future__ import annotations

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.freebox_caller_id.const import (
    EVENT_INCOMING_CALL,
)
from custom_components.freebox_caller_id.coordinator import (
    FreeboxCallerCoordinator,
)

FREEBOX_HOST = "192.168.1.254"
APP_TOKEN = "test-app-token"
ENTRY_ID = "test-entry-id"
SESSION_TOKEN = "test-session-token"
CHALLENGE = "test-challenge"
FIRMWARE = "4.8.1"
MODEL = "Freebox Ultra"


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
            "result": {
                "firmware_version": FIRMWARE,
                "model_info": {
                    "pretty_name": MODEL,
                },
            },
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

    events = []
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

    events = []
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

    events = []
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

    events = []
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
        "system": {
            "firmware_version": FIRMWARE,
            "model_info": {
                "pretty_name": MODEL,
            },
        },
    }


@pytest.mark.parametrize(
    ("call_type", "expected"),
    [
        ("accepted", True),
        ("missed", True),
        ("outgoing", False),
    ],
)
def test_is_incoming(
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
def test_is_ringing_uses_duration_zero(
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


def test_is_ringing_expires_after_timeout(
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


async def test_session_expired_is_renewed(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test that a 403 on the call log causes session renewal."""
    base_url = f"http://{FREEBOX_HOST}"

    aioclient_mock.get(
        f"{base_url}/api/v4/system/",
        json={
            "success": True,
            "result": {
                "firmware_version": FIRMWARE,
                "model_info": {
                    "pretty_name": MODEL,
                },
            },
        },
    )

    # First call-log response expires the session.
    aioclient_mock.get(
        f"{base_url}/api/v4/call/log/",
        status=403,
    )

    _login_responses(aioclient_mock)

    # The retry uses the renewed session.
    aioclient_mock.get(
        f"{base_url}/api/v4/call/log/",
        status=200,
        json={
            "success": True,
            "result": [],
        },
    )

    coordinator = _create_coordinator(hass)
    coordinator.session_token = "expired-token"

    data = await coordinator._async_update_data()

    assert coordinator.session_token == SESSION_TOKEN
    assert data["system"]["firmware_version"] == FIRMWARE


async def test_system_info_is_cached(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test that system information is not fetched on every update."""
    _system_response(aioclient_mock)
    _call_log_response(
        aioclient_mock,
        None,
    )

    coordinator = _create_coordinator(hass)
    coordinator.session_token = SESSION_TOKEN

    await coordinator._async_update_data()

    assert len(aioclient_mock.mock_calls) >= 2

    # The second update only needs call-log because system_info is cached.
    _call_log_response(
        aioclient_mock,
        None,
    )

    await coordinator._async_update_data()

    system_requests = [
        call
        for call in aioclient_mock.mock_calls
        if "/api/v4/system/" in str(call)
    ]

    assert len(system_requests) == 1
