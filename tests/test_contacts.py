"""Tests for on-demand Freebox contact lookup."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest

from custom_components.freebox_caller_id.coordinator import (
    FreeboxCallerCoordinator,
    FreeboxContactApiError,
    FreeboxContactPermissionError,
)
from custom_components.freebox_caller_id.services import (
    _find_contacts_by_name,
    _find_contacts_by_number,
)
from custom_components.freebox_caller_id.types import FreeboxContact

FREEBOX_HOST = "192.168.1.254"
APP_TOKEN = "test-app-token"
ENTRY_ID = "test-entry-id"
SESSION_TOKEN = "test-session-token"

CONTACTS: list[FreeboxContact] = [
    {
        "id": 1,
        "display_name": "Alice Martin",
        "first_name": "Alice",
        "last_name": "Martin",
        "numbers": [
            {"number": "06 12 34 56 78", "type": "mobile"},
            {"number": "+33 (0)1-22-33-44-55", "type": "home"},
        ],
    },
    {
        "id": 2,
        "display_name": "Service Client",
        "company": "Acme",
        "numbers": [{"number": "01.23.45.67.89", "label": "Bureau"}],
    },
]


def _create_coordinator(hass: HomeAssistant) -> FreeboxCallerCoordinator:
    """Create a coordinator for contact tests."""
    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=async_get_clientsession(hass),
        host=FREEBOX_HOST,
        app_token=APP_TOKEN,
        entry_id=ENTRY_ID,
        scan_interval=2,
        ringing_timeout=45,
    )
    coordinator.session_token = SESSION_TOKEN
    return coordinator


def test_find_contacts_by_number() -> None:
    """Match exact numbers while ignoring common display formatting."""
    matches = _find_contacts_by_number(CONTACTS, "06-12-34-56-78")
    assert len(matches) == 1
    assert matches[0]["display_name"] == "Alice Martin"
    assert matches[0]["matched_number"] == "06 12 34 56 78"
    assert _find_contacts_by_number(CONTACTS, "0612345670") == []


def test_find_contacts_by_name() -> None:
    """Match name fields case-insensitively and allow multiple results."""
    matches = _find_contacts_by_name(CONTACTS, "ALICE")
    assert [item["display_name"] for item in matches] == ["Alice Martin"]
    assert _find_contacts_by_name(CONTACTS, "acme")[0]["company"] == "Acme"
    assert len(_find_contacts_by_name(CONTACTS, "i")) == 2


async def test_get_contacts_success(hass: HomeAssistant, aioclient_mock) -> None:
    """Return contacts received from the Freebox API."""
    coordinator = _create_coordinator(hass)
    aioclient_mock.get(
        f"http://{FREEBOX_HOST}/api/v4/contact/?limit=-1",
        json={"success": True, "result": CONTACTS},
    )

    contacts = await coordinator.async_get_contacts()

    assert contacts == CONTACTS


async def test_get_contacts_permission_denied(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Identify a contacts permission denial from the Freebox API."""
    coordinator = _create_coordinator(hass)
    aioclient_mock.get(
        f"http://{FREEBOX_HOST}/api/v4/contact/?limit=-1",
        status=403,
        json={"success": False, "error_code": "insufficient_rights"},
    )

    with pytest.raises(FreeboxContactPermissionError):
        await coordinator.async_get_contacts()


async def test_get_contacts_invalid_response(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Reject an unsuccessful response rather than return no contacts."""
    coordinator = _create_coordinator(hass)
    aioclient_mock.get(
        f"http://{FREEBOX_HOST}/api/v4/contact/?limit=-1",
        json={"success": False, "result": []},
    )

    with pytest.raises(FreeboxContactApiError):
        await coordinator.async_get_contacts()
