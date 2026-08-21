"""Tests for the Freebox Caller ID coordinator."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.freebox_caller_id.const import (
    DOMAIN,
    EVENT_INCOMING_CALL,
)
from custom_components.freebox_caller_id.coordinator import (
    FreeboxCallerCoordinator,
)

HOST = "192.168.1.254"
APP_TOKEN = "test-app-token"
ENTRY_ID = "test-entry-id"


class FakeResponse:
    """Minimal async context manager for aiohttp responses."""

    def __init__(
        self,
        payload: dict[str, object],
        status: int = 200,
    ) -> None:
        """Initialize the fake response."""
        self.status = status
        self._payload = payload

    async def __aenter__(self) -> FakeResponse:
        """Enter the async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        """Exit the async context manager."""

    async def json(self) -> dict[str, object]:
        """Return the fake JSON response."""
        return self._payload


class FakeSession:
    """Minimal session returning a predefined call-log response."""

    def __init__(
        self,
        call_log: dict[str, object],
    ) -> None:
        """Initialize the fake session."""
        self.call_log = call_log

    def get(
        self,
        url: str,
        **kwargs: object,
    ) -> FakeResponse:
        """Return a fake call-log response."""
        return FakeResponse(self.call_log)


def _create_coordinator(
    hass: HomeAssistant,
    call_log: dict[str, object],
) -> FreeboxCallerCoordinator:
    """Create a coordinator for tests."""
    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=FakeSession(call_log),  # type: ignore[arg-type]
        host=HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )
    coordinator.session_token = "test-session-token"
    return coordinator


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


def _call_log(
    call: dict[str, object] | None,
) -> dict[str, object]:
    """Build a call-log API response."""
    return {
        "success": True,
        "result": [] if call is None else [call],
    }


async def _prepare_update(
    coordinator: FreeboxCallerCoordinator,
) -> None:
    """Prepare the coordinator for a direct update test."""
    coordinator._async_fetch_system_info = AsyncMock(  # noqa: SLF001
    )
    coordinator._async_get_session = AsyncMock(  # noqa: SLF001
        return_value=True,
    )


async def test_first_call_initializes_without_event(
    hass: HomeAssistant,
) -> None:
    """Test that the first call only initializes the last seen ID."""
    call = _call(
        call_id=1,
        call_type="accepted",
        duration=0,
    )

    coordinator = _create_coordinator(
        hass,
        _call_log(call),
    )
    await _prepare_update(coordinator)

    events: list[object] = []
    hass.bus.async_listen(
        EVENT_INCOMING_CALL,
        lambda event: events.append(event),
    )

    data = await coordinator._async_update_data()  # noqa: SLF001

    assert coordinator._last_seen_call_id == 1  # noqa: SLF001
    assert events == []
    assert data["is_ringing"] is True


async def test_new_incoming_call_fires_event(
    hass: HomeAssistant,
) -> None:
    """Test that a new incoming call fires an event."""
    call = _call(
        call_id=2,
        call_type="missed",
        duration=0,
    )

    coordinator = _create_coordinator(
        hass,
        _call_log(call),
    )
    coordinator._last_seen_call_id = 1  # noqa: SLF001
    await _prepare_update(coordinator)

    events: list[object] = []
    hass.bus.async_listen(
        EVENT_INCOMING_CALL,
        lambda event: events.append(event),
    )

    await coordinator._async_update_data()  # noqa: SLF001

    assert coordinator._last_seen_call_id == 2  # noqa: SLF001
    assert len(events) == 1

    event = events[0]
    assert event.data["id"] == 2
    assert event.data["number"] == "0123456789"
    assert event.data["name"] == "Test Caller"
    assert event.data["type"] == "missed"


async def test_outgoing_call_does_not_fire_event(
    hass: HomeAssistant,
) -> None:
    """Test that a new outgoing call does not fire an event."""
    call = _call(
        call_id=2,
        call_type="outgoing",
        duration=10,
    )

    coordinator = _create_coordinator(
        hass,
        _call_log(call),
    )
    coordinator._last_seen_call_id = 1  # noqa: SLF001
    await _prepare_update(coordinator)

    events: list[object] = []
    hass.bus.async_listen(
        EVENT_INCOMING_CALL,
        lambda event: events.append(event),
    )

    data = await coordinator._async_update_data()  # noqa: SLF001

    assert coordinator._last_seen_call_id == 2  # noqa: SLF001
    assert events == []
    assert data["is_ringing"] is False


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
    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=FakeSession(_call_log(None)),  # type: ignore[arg-type]
        host=HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )

    assert coordinator._is_incoming(call_type) is expected  # noqa: SLF001


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
    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=FakeSession(_call_log(None)),  # type: ignore[arg-type]
        host=HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )

    assert (
        coordinator._is_ringing(  # noqa: SLF001
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
    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=FakeSession(_call_log(None)),  # type: ignore[arg-type]
        host=HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )

    assert (
        coordinator._is_ringing(  # noqa: SLF001
            call_type="accepted",
            duration=0,
            call_time=1_000,
            now=1_044,
        )
        is True
    )

    assert (
        coordinator._is_ringing(  # noqa: SLF001
            call_type="accepted",
            duration=0,
            call_time=1_000,
            now=1_045,
        )
        is False
    )


async def test_empty_call_log_is_valid(
    hass: HomeAssistant,
) -> None:
    """Test that an empty call log does not fail."""
    coordinator = _create_coordinator(
        hass,
        _call_log(None),
    )
    await _prepare_update(coordinator)

    data = await coordinator._async_update_data()  # noqa: SLF001

    assert data == {
        "system": {},
    }


async def test_update_failed_clears_system_info(
    hass: HomeAssistant,
) -> None:
    """Test that an update failure clears system info."""
    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=FakeSession(_call_log(None)),  # type: ignore[arg-type]
        host=HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )
    coordinator.session_token = "existing-token"
    coordinator.system_info = {
        "firmware_version": "4.8.0",
    }

    original_device_info = coordinator.device_info

    with pytest.raises(UpdateFailed):
        coordinator._handle_failure("Freebox unavailable")  # noqa: SLF001

    assert coordinator.session_token is None
    assert coordinator.system_info == {}
    assert coordinator.device_info is original_device_info
