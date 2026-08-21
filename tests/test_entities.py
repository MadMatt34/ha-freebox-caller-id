"""Tests for the Freebox Caller ID entities."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.freebox_caller_id import FreeboxConfigEntry
from custom_components.freebox_caller_id.binary_sensor import (
    FreeboxRingingSensor,
)
from custom_components.freebox_caller_id.const import (
    CONF_APP_TOKEN,
    CONF_HOST,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)
from custom_components.freebox_caller_id.coordinator import (
    FreeboxCallerCoordinator,
)
from custom_components.freebox_caller_id.entity import FreeboxCallerIDEntity
from custom_components.freebox_caller_id.sensor import FreeboxLastCallSensor

FREEBOX_HOST = "192.168.1.254"
APP_TOKEN = "test-app-token"
ENTRY_ID = "test-entry-id"
SESSION_TOKEN = "test-session-token"


def _create_entry() -> MockConfigEntry:
    """Create a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Freebox Caller ID",
        unique_id="test-freebox-uid",
        data={
            CONF_HOST: FREEBOX_HOST,
            CONF_APP_TOKEN: APP_TOKEN,
            CONF_SCAN_INTERVAL: 2,
        },
    )


def _create_coordinator(
    hass: HomeAssistant,
    entry: FreeboxConfigEntry,
) -> FreeboxCallerCoordinator:
    """Create a coordinator for entity tests."""
    return FreeboxCallerCoordinator(
        hass=hass,
        session=async_get_clientsession(hass),
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=entry.entry_id,
        scan_interval=2,
        ringing_timeout=45,
    )


async def test_sensor_setup_and_entity(
    hass: HomeAssistant,
) -> None:
    """Test sensor platform setup and entity properties."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    coordinator = _create_coordinator(hass, entry)
    coordinator._data = {
        "is_ringing": False,
        "caller_name": "Jean Dupont",
        "caller_number": "0123456789",
        "call_type": "accepted",
        "duration": 42,
        "datetime": 1_700_000_000.0,
        "id": 10,
        "recent_calls": [
            {
                "id": 10,
                "number": "0123456789",
                "name": "Jean Dupont",
                "type": "accepted",
                "duration": 42,
                "timestamp": 1_700_000_000.0,
            }
        ],
        "system": {
            "firmware_version": "4.8.1",
            "model_info": {
                "pretty_name": "Freebox Ultra",
            },
        },
    }

    entities: list[Any] = []

    async def async_add_entities(new_entities: list[Any]) -> None:
        """Capture added entities."""
        entities.extend(new_entities)

    await _setup_sensor(
        hass,
        entry,
        coordinator,
        async_add_entities,
    )

    assert len(entities) == 1
    entity = entities[0]

    assert isinstance(entity, FreeboxLastCallSensor)
    assert isinstance(entity, FreeboxCallerIDEntity)
    assert entity.unique_id == f"{entry.entry_id}_last_call"
    assert entity.has_entity_name is True
    assert entity.translation_key == "last_call"
    assert entity.device_info == coordinator.device_info

    assert entity.native_value == "Jean Dupont"
    assert entity.extra_state_attributes == {
        "number": "0123456789",
        "name": "Jean Dupont",
        "type": "accepted",
        "duration": 42,
        "timestamp": 1_700_000_000.0,
        "calls": [
            {
                "id": 10,
                "number": "0123456789",
                "name": "Jean Dupont",
                "type": "accepted",
                "duration": 42,
                "timestamp": 1_700_000_000.0,
            }
        ],
    }


async def test_sensor_uses_number_when_name_is_unknown(
    hass: HomeAssistant,
) -> None:
    """Test the sensor fallback to the caller number."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    coordinator = _create_coordinator(hass, entry)
    coordinator._data = {
        "caller_name": "Inconnu",
        "caller_number": "0123456789",
        "recent_calls": [],
    }

    entity = FreeboxLastCallSensor(
        coordinator,
        entry,
    )

    assert entity.native_value == "0123456789"


async def test_sensor_uses_default_when_no_data(
    hass: HomeAssistant,
) -> None:
    """Test sensor values when no coordinator data is available."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    coordinator = _create_coordinator(hass, entry)
    coordinator._data = None

    entity = FreeboxLastCallSensor(
        coordinator,
        entry,
    )

    assert entity.native_value == "Aucun"
    assert entity.extra_state_attributes == {
        "calls": [],
    }


async def test_sensor_uses_default_when_number_is_missing(
    hass: HomeAssistant,
) -> None:
    """Test sensor fallback when neither a name nor number exists."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    coordinator = _create_coordinator(hass, entry)
    coordinator._data = {
        "caller_name": "Inconnu",
        "caller_number": None,
        "recent_calls": [],
    }

    entity = FreeboxLastCallSensor(
        coordinator,
        entry,
    )

    assert entity.native_value == "Aucun"


async def test_binary_sensor_setup_and_entity(
    hass: HomeAssistant,
) -> None:
    """Test binary sensor platform setup and entity properties."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    coordinator = _create_coordinator(hass, entry)
    coordinator._data = {
        "is_ringing": True,
        "caller_name": "Jean Dupont",
        "caller_number": "0123456789",
        "call_type": "accepted",
        "datetime": 1_700_000_000.0,
    }

    entities: list[Any] = []

    async def async_add_entities(new_entities: list[Any]) -> None:
        """Capture added entities."""
        entities.extend(new_entities)

    await _setup_binary_sensor(
        hass,
        entry,
        coordinator,
        async_add_entities,
    )

    assert len(entities) == 1
    entity = entities[0]

    assert isinstance(entity, FreeboxRingingSensor)
    assert isinstance(entity, FreeboxCallerIDEntity)
    assert entity.unique_id == f"{entry.entry_id}_ringing"
    assert entity.has_entity_name is True
    assert entity.translation_key == "ringing"
    assert entity.device_class == "sound"
    assert entity.device_info == coordinator.device_info

    assert entity.is_on is True
    assert entity.extra_state_attributes == {
        "caller_name": "Jean Dupont",
        "caller_number": "0123456789",
        "call_type": "accepted",
        "datetime": 1_700_000_000.0,
    }


async def test_binary_sensor_is_off_without_data(
    hass: HomeAssistant,
) -> None:
    """Test binary sensor state when no coordinator data is available."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    coordinator = _create_coordinator(hass, entry)
    coordinator._data = None

    entity = FreeboxRingingSensor(
        coordinator,
        entry,
    )

    assert entity.is_on is False
    assert entity.extra_state_attributes == {}


async def test_binary_sensor_is_off_when_not_ringing(
    hass: HomeAssistant,
) -> None:
    """Test binary sensor state when a call is not ringing."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    coordinator = _create_coordinator(hass, entry)
    coordinator._data = {
        "is_ringing": False,
        "caller_name": "Jean Dupont",
        "caller_number": "0123456789",
        "call_type": "accepted",
        "datetime": 1_700_000_000.0,
    }

    entity = FreeboxRingingSensor(
        coordinator,
        entry,
    )

    assert entity.is_on is False
    assert entity.extra_state_attributes == {}


async def _setup_sensor(
    hass: HomeAssistant,
    entry: FreeboxConfigEntry,
    coordinator: FreeboxCallerCoordinator,
    async_add_entities: Any,
) -> None:
    """Run the sensor platform setup with a prepared coordinator."""
    entry.runtime_data = coordinator

    from custom_components.freebox_caller_id import sensor

    await sensor.async_setup_entry(
        hass,
        entry,
        async_add_entities,
    )


async def _setup_binary_sensor(
    hass: HomeAssistant,
    entry: FreeboxConfigEntry,
    coordinator: FreeboxCallerCoordinator,
    async_add_entities: Any,
) -> None:
    """Run the binary sensor platform setup with a prepared coordinator."""
    entry.runtime_data = coordinator

    from custom_components.freebox_caller_id import binary_sensor

    await binary_sensor.async_setup_entry(
        hass,
        entry,
        async_add_entities,
    )
