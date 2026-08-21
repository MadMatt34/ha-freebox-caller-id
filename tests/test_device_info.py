"""Tests for Freebox Caller ID DeviceInfo handling."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.freebox_caller_id.const import DOMAIN
from custom_components.freebox_caller_id.coordinator import (
    FreeboxCallerCoordinator,
)

FREEBOX_HOST = "192.168.1.254"
APP_TOKEN = "test-app-token"
ENTRY_ID = "test-entry-id"


def _create_coordinator(
    hass: HomeAssistant,
) -> FreeboxCallerCoordinator:
    """Create a coordinator for DeviceInfo tests."""
    return FreeboxCallerCoordinator(
        hass=hass,
        session=async_get_clientsession(hass),
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )


def test_default_device_info(
    hass: HomeAssistant,
) -> None:
    """Test the initial DeviceInfo."""
    coordinator = _create_coordinator(hass)

    device_info = coordinator.device_info

    assert device_info["identifiers"] == {
        (DOMAIN, ENTRY_ID),
    }
    assert device_info["name"] == "Freebox Phone"
    assert device_info["manufacturer"] == "Free"
    assert device_info["model"] == "Freebox Server"
    assert device_info.get("sw_version") is None
    assert device_info["configuration_url"] == f"http://{FREEBOX_HOST}"


def test_device_info_updates_from_model_info(
    hass: HomeAssistant,
) -> None:
    """Test DeviceInfo update from Freebox system information."""
    coordinator = _create_coordinator(hass)

    coordinator.system_info = {
        "firmware_version": "4.8.1",
        "model_info": {
            "pretty_name": "Freebox Ultra",
            "name": "ultra",
        },
    }

    coordinator._update_device_info()  # noqa: SLF001

    device_info = coordinator.device_info

    assert device_info["model"] == "Freebox Server (modèle Freebox Ultra)"
    assert device_info["sw_version"] == "4.8.1"


def test_device_info_falls_back_to_board_name(
    hass: HomeAssistant,
) -> None:
    """Test the board_name fallback."""
    coordinator = _create_coordinator(hass)

    coordinator.system_info = {
        "firmware_version": "4.8.2",
        "board_name": "Freebox Delta",
    }

    coordinator._update_device_info()  # noqa: SLF001

    assert coordinator.device_info["model"] == (
        "Freebox Server (modèle Freebox Delta)"
    )
    assert coordinator.device_info["sw_version"] == "4.8.2"


def test_device_info_does_not_rebuild_when_unchanged(
    hass: HomeAssistant,
) -> None:
    """Test that an unchanged signature reuses the cached DeviceInfo."""
    coordinator = _create_coordinator(hass)

    coordinator.system_info = {
        "firmware_version": "4.8.1",
        "model_info": {
            "pretty_name": "Freebox Ultra",
        },
    }

    coordinator._update_device_info()  # noqa: SLF001
    device_info = coordinator.device_info

    coordinator._update_device_info()  # noqa: SLF001

    assert coordinator.device_info is device_info


def test_device_info_updates_existing_device_metadata(
    hass: HomeAssistant,
) -> None:
    """Test that technical metadata is updated on an existing device."""
    coordinator = _create_coordinator(hass)

    device_registry = dr.async_get(hass)

    device = device_registry.async_get_or_create(
        config_entry_id=ENTRY_ID,
        identifiers={(DOMAIN, ENTRY_ID)},
        name="Freebox Phone",
        manufacturer="Free",
        model="Freebox Server",
        area_id="area_bureau",
    )

    device_registry.async_update_device(
        device.id,
        name_by_user="Téléphone fixe",
        area_id="area_bureau",
    )

    coordinator.system_info = {
        "firmware_version": "4.8.3",
        "model_info": {
            "pretty_name": "Freebox Ultra",
        },
    }

    coordinator._update_device_info()  # noqa: SLF001

    updated_device = device_registry.async_get(device.id)

    assert updated_device is not None
    assert updated_device.name_by_user == "Téléphone fixe"
    assert updated_device.area_id == "area_bureau"
    assert updated_device.manufacturer == "Free"
    assert updated_device.model == "Freebox Server (modèle Freebox Ultra)"
    assert updated_device.sw_version == "4.8.3"


def test_device_info_is_preserved_when_system_info_is_cleared(
    hass: HomeAssistant,
) -> None:
    """Test that the cached DeviceInfo survives a connection loss."""
    coordinator = _create_coordinator(hass)

    coordinator.system_info = {
        "firmware_version": "4.8.1",
        "model_info": {
            "pretty_name": "Freebox Ultra",
        },
    }

    coordinator._update_device_info()  # noqa: SLF001

    device_info = coordinator.device_info

    coordinator.system_info = {}

    assert coordinator.device_info is device_info
    assert coordinator.device_info["model"] == (
        "Freebox Server (modèle Freebox Ultra)"
    )
    assert coordinator.device_info["sw_version"] == "4.8.1"
