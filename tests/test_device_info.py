"""Tests for Freebox Caller ID DeviceInfo handling."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.freebox_caller_id.const import DOMAIN
from custom_components.freebox_caller_id.coordinator import (
    FreeboxCallerCoordinator,
)

HOST = "192.168.1.254"
APP_TOKEN = "test-app-token"
ENTRY_ID = "test-entry-id"


class FakeSession:
    """Minimal session for DeviceInfo tests."""


def _create_coordinator(
    hass: HomeAssistant,
) -> FreeboxCallerCoordinator:
    """Create a coordinator for DeviceInfo tests."""
    return FreeboxCallerCoordinator(
        hass=hass,
        session=FakeSession(),  # type: ignore[arg-type]
        host=HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )


def _device_info_signature(
    coordinator: FreeboxCallerCoordinator,
) -> tuple[object, ...]:
    """Return the current DeviceInfo values relevant to the tests."""
    device_info = coordinator.device_info

    return (
        device_info["name"],
        device_info["manufacturer"],
        device_info["model"],
        device_info.get("sw_version"),
        device_info["configuration_url"],
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
    assert device_info["configuration_url"] == f"http://{HOST}"


def test_device_info_updates_from_system_info(
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
    """Test fallback to board_name when model_info has no model."""
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


def test_device_info_not_rebuilt_when_signature_is_unchanged(
    hass: HomeAssistant,
) -> None:
    """Test that identical system information does not rebuild DeviceInfo."""
    coordinator = _create_coordinator(hass)

    coordinator.system_info = {
        "firmware_version": "4.8.1",
        "model_info": {
            "pretty_name": "Freebox Ultra",
        },
    }

    coordinator._update_device_info()  # noqa: SLF001
    device_info = coordinator.device_info
    signature = _device_info_signature(coordinator)

    coordinator._update_device_info()  # noqa: SLF001

    assert coordinator.device_info is device_info
    assert _device_info_signature(coordinator) == signature


def test_device_info_update_preserves_user_controlled_device_fields(
    hass: HomeAssistant,
) -> None:
    """Test that a technical update does not overwrite area or user name."""
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
    """Test that DeviceInfo stays cached while the Freebox is unavailable."""
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
