"""Tests for Freebox Caller ID diagnostics."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.freebox_caller_id.const import (
    CONF_APP_TOKEN,
    CONF_HOST,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)
from custom_components.freebox_caller_id.diagnostics import (
    async_get_config_entry_diagnostics,
)

FREEBOX_HOST = "192.168.1.254"
APP_TOKEN = "test-app-token"
ENTRY_ID = "test-entry-id"


def _create_entry() -> MockConfigEntry:
    """Create a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Freebox Caller ID",
        unique_id="test-freebox-uid",
        version=1,
        data={
            CONF_HOST: FREEBOX_HOST,
            CONF_APP_TOKEN: APP_TOKEN,
            CONF_SCAN_INTERVAL: 2,
        },
        options={
            CONF_SCAN_INTERVAL: 5,
        },
    )


def _create_coordinator() -> MagicMock:
    """Create a coordinator mock for diagnostics."""
    coordinator = MagicMock()
    coordinator.data = {
        "is_ringing": True,
        "caller_name": "Jean Dupont",
        "caller_number": "0123456789",
        "call_type": "accepted",
        "duration": 0,
        "datetime": 1_700_000_000.0,
        "id": 42,
        "recent_calls": [
            {
                "id": 42,
                "number": "0123456789",
                "name": "Jean Dupont",
                "type": "accepted",
                "duration": 0,
                "timestamp": 1_700_000_000.0,
            },
            {
                "id": 41,
                "number": "0987654321",
                "name": "Marie Martin",
                "type": "missed",
                "duration": 0,
                "timestamp": 1_699_999_000.0,
            },
        ],
    }
    coordinator.last_update_success = True
    coordinator.update_interval = timedelta(seconds=5)

    return coordinator


async def test_diagnostics_redact_sensitive_data(
    hass: HomeAssistant,
) -> None:
    """Test that diagnostics redact secrets and personal data."""
    entry = _create_entry()
    entry.add_to_hass(hass)
    entry.runtime_data = _create_coordinator()

    diagnostics = await async_get_config_entry_diagnostics(
        hass,
        entry,
    )

    assert diagnostics["entry"]["entry_id"] == entry.entry_id
    assert diagnostics["entry"]["version"] == 1
    assert diagnostics["entry"]["data"] == {
        CONF_HOST: "**REDACTED**",
        CONF_APP_TOKEN: "**REDACTED**",
        CONF_SCAN_INTERVAL: 2,
    }
    assert diagnostics["entry"]["options"] == {
        CONF_SCAN_INTERVAL: 5,
    }

    assert diagnostics["coordinator"]["last_update_success"] is True
    assert diagnostics["coordinator"]["update_interval"] == "0:00:05"

    data = diagnostics["coordinator"]["data"]

    assert data["is_ringing"] is True
    assert data["duration"] == 0
    assert data["id"] == 42

    assert data["caller_name"] == "**REDACTED**"
    assert data["caller_number"] == "**REDACTED**"

    assert data["recent_calls"] == [
        {
            "id": 42,
            "number": "**REDACTED**",
            "name": "**REDACTED**",
            "type": "accepted",
            "duration": 0,
            "timestamp": 1_700_000_000.0,
        },
        {
            "id": 41,
            "number": "**REDACTED**",
            "name": "**REDACTED**",
            "type": "missed",
            "duration": 0,
            "timestamp": 1_699_999_000.0,
        },
    ]


async def test_diagnostics_redact_nested_sensitive_fields(
    hass: HomeAssistant,
) -> None:
    """Test that nested sensitive keys are also redacted."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    coordinator = MagicMock()
    coordinator.data = {
        "nested": {
            "app_token": "secret",
            "session_token": "session-secret",
            "host": FREEBOX_HOST,
            "name": "Private name",
            "number": "0123456789",
            "safe_value": "kept",
        },
    }
    coordinator.last_update_success = False
    coordinator.update_interval = None
    entry.runtime_data = coordinator

    diagnostics = await async_get_config_entry_diagnostics(
        hass,
        entry,
    )

    data = diagnostics["coordinator"]["data"]

    assert data["nested"] == {
        "app_token": "**REDACTED**",
        "session_token": "**REDACTED**",
        "host": "**REDACTED**",
        "name": "**REDACTED**",
        "number": "**REDACTED**",
        "safe_value": "kept",
    }
    assert diagnostics["coordinator"]["last_update_success"] is False
    assert diagnostics["coordinator"]["update_interval"] is None


async def test_diagnostics_handles_empty_coordinator_data(
    hass: HomeAssistant,
) -> None:
    """Test diagnostics when the coordinator has no data."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    coordinator = MagicMock()
    coordinator.data = None
    coordinator.last_update_success = False
    coordinator.update_interval = timedelta(seconds=2)
    entry.runtime_data = coordinator

    diagnostics = await async_get_config_entry_diagnostics(
        hass,
        entry,
    )

    assert diagnostics["coordinator"]["data"] == {}
    assert diagnostics["coordinator"]["last_update_success"] is False
    assert diagnostics["coordinator"]["update_interval"] == "0:00:02"
