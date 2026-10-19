"""Tests for on-demand Freebox contact lookup."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryAuthFailed, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest

from custom_components.freebox_caller_id.const import DOMAIN
from custom_components.freebox_caller_id.coordinator import (
    FreeboxCallerCoordinator,
    FreeboxContactApiError,
    FreeboxContactPermissionError,
)
from custom_components.freebox_caller_id.services import (
    _contact_result,
    _find_contacts_by_name,
    _find_contacts_by_number,
    _get_coordinator,
    _translate_contact_error,
    async_setup_services,
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


SERVICE_INPUTS = (
    ("contact_by_number", "phone_number", "06-12-34-56-78"),
    ("contact_by_name", "name", "Alice"),
)


def _loaded_entry(coordinator: FreeboxCallerCoordinator | MagicMock) -> SimpleNamespace:
    """Create a loaded config entry stand-in."""
    return SimpleNamespace(
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=coordinator,
    )


@pytest.mark.parametrize(("service_name", "input_key", "input_value"), SERVICE_INPUTS)
async def test_services_contact_lookup_success(
    hass: HomeAssistant,
    service_name: str,
    input_key: str,
    input_value: str,
) -> None:
    """Return structured matches from both contact lookup actions."""
    coordinator = MagicMock()
    coordinator.async_get_contacts = AsyncMock(return_value=CONTACTS)
    async_setup_services(hass)
    with patch.object(
        hass.config_entries,
        "async_get_entry",
        return_value=_loaded_entry(coordinator),
    ):
        result = await hass.services.async_call(
            DOMAIN,
            service_name,
            {"config_entry_id": ENTRY_ID, input_key: input_value},
            blocking=True,
            return_response=True,
        )
    assert isinstance(result, dict)
    assert len(result["matches"]) == 1
    coordinator.async_get_contacts.assert_awaited_once()


@pytest.mark.parametrize(("service_name", "input_key", "_"), SERVICE_INPUTS)
async def test_services_empty_search_is_rejected(
    hass: HomeAssistant,
    service_name: str,
    input_key: str,
    _: str,
) -> None:
    """Reject empty input before querying the Freebox."""
    async_setup_services(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            service_name,
            {"config_entry_id": ENTRY_ID, input_key: "   "},
            blocking=True,
            return_response=True,
        )


@pytest.mark.parametrize(("service_name", "input_key", "input_value"), SERVICE_INPUTS)
async def test_services_report_contacts_permission_error(
    hass: HomeAssistant,
    service_name: str,
    input_key: str,
    input_value: str,
) -> None:
    """Expose a translated error if contact-list permission is denied."""
    coordinator = MagicMock()
    coordinator.async_get_contacts = AsyncMock(side_effect=FreeboxContactPermissionError)
    async_setup_services(hass)
    with (
        patch.object(
            hass.config_entries, "async_get_entry",
            return_value=_loaded_entry(coordinator),
        ),
        pytest.raises(HomeAssistantError) as exc_info,
    ):
        await hass.services.async_call(
            DOMAIN, service_name,
            {"config_entry_id": ENTRY_ID, input_key: input_value},
            blocking=True, return_response=True,
        )
    assert exc_info.value.translation_key == "contacts_permission_denied"


@pytest.mark.parametrize(("service_name", "input_key", "input_value"), SERVICE_INPUTS)
async def test_services_report_contacts_api_error(
    hass: HomeAssistant,
    service_name: str,
    input_key: str,
    input_value: str,
) -> None:
    """Expose a translated error if the contacts request fails."""
    coordinator = MagicMock()
    coordinator.async_get_contacts = AsyncMock(side_effect=FreeboxContactApiError)
    async_setup_services(hass)
    with (
        patch.object(
            hass.config_entries, "async_get_entry",
            return_value=_loaded_entry(coordinator),
        ),
        pytest.raises(HomeAssistantError) as exc_info,
    ):
        await hass.services.async_call(
            DOMAIN, service_name,
            {"config_entry_id": ENTRY_ID, input_key: input_value},
            blocking=True, return_response=True,
        )
    assert exc_info.value.translation_key == "contact_lookup_failed"


@pytest.mark.parametrize(("service_name", "input_key", "input_value"), SERVICE_INPUTS)
async def test_services_report_invalid_app_token(
    hass: HomeAssistant,
    service_name: str,
    input_key: str,
    input_value: str,
) -> None:
    """Expose a translated authentication error if the app token is revoked."""
    coordinator = MagicMock()
    coordinator.async_get_contacts = AsyncMock(
        side_effect=ConfigEntryAuthFailed("invalid token")
    )
    async_setup_services(hass)
    with (
        patch.object(
            hass.config_entries, "async_get_entry",
            return_value=_loaded_entry(coordinator),
        ),
        pytest.raises(HomeAssistantError) as exc_info,
    ):
        await hass.services.async_call(
            DOMAIN, service_name,
            {"config_entry_id": ENTRY_ID, input_key: input_value},
            blocking=True, return_response=True,
        )
    assert exc_info.value.translation_key == "invalid_app_token"


def test_contact_result_filters_invalid_values() -> None:
    """Return valid contact fields only and skip malformed numbers."""
    result = _contact_result({
        "id": "not-an-int",
        "display_name": "",
        "numbers": [None, {}, {"number": 123}, {"number": "0123456789", "type": 5, "label": ""}],
    })
    assert result == {"numbers": [{"number": "0123456789"}]}


def test_contact_result_with_matched_number() -> None:
    """Include a matched number and optional contact fields."""
    result = _contact_result(
        {
            "id": 1,
            "display_name": "Alice",
            "first_name": "Alice",
            "last_name": "Martin",
            "company": "Acme",
            "numbers": [{"number": "0123456789", "type": "home", "label": "Maison"}],
        },
        matched_number="0123456789",
    )
    assert result["matched_number"] == "0123456789"
    assert result["numbers"] == [
        {"number": "0123456789", "type": "home", "label": "Maison"}
    ]


def test_contact_search_skips_malformed_contact_values() -> None:
    """Ignore malformed number collections, entries, and number fields."""
    contacts: list[FreeboxContact] = [
        {"numbers": []},
        {"numbers": [None, {}, {"number": 22}]},  # type: ignore[list-item]
        {"numbers": "not-a-list"},  # type: ignore[typeddict-item]
    ]
    assert _find_contacts_by_number(contacts, "22") == []
    assert _find_contacts_by_name(contacts, "missing") == []


def test_get_coordinator_rejects_missing_or_wrong_domain(hass: HomeAssistant) -> None:
    """Reject missing config entries and entries from another integration."""
    with (
        patch.object(hass.config_entries, "async_get_entry", return_value=None),
        pytest.raises(ServiceValidationError) as exc_info,
    ):
        _get_coordinator(hass, ENTRY_ID)
    assert exc_info.value.translation_key == "config_entry_not_found"

    with (
        patch.object(
            hass.config_entries, "async_get_entry",
            return_value=SimpleNamespace(domain="other", state=ConfigEntryState.LOADED),
        ),
        pytest.raises(ServiceValidationError) as exc_info,
    ):
        _get_coordinator(hass, ENTRY_ID)
    assert exc_info.value.translation_key == "config_entry_not_found"


def test_get_coordinator_rejects_not_loaded_entry(hass: HomeAssistant) -> None:
    """Reject config entries that are not loaded."""
    with (
        patch.object(
            hass.config_entries, "async_get_entry",
            return_value=SimpleNamespace(domain=DOMAIN, state=ConfigEntryState.NOT_LOADED),
        ),
        pytest.raises(ServiceValidationError) as exc_info,
    ):
        _get_coordinator(hass, ENTRY_ID)
    assert exc_info.value.translation_key == "config_entry_not_loaded"


def test_translate_contact_errors() -> None:
    """Map known failures to user-facing translated errors."""
    assert _translate_contact_error(FreeboxContactPermissionError()).translation_key == "contacts_permission_denied"
    assert _translate_contact_error(FreeboxContactApiError()).translation_key == "contact_lookup_failed"
    assert _translate_contact_error(ConfigEntryAuthFailed("invalid token")).translation_key == "invalid_app_token"


async def test_get_contacts_failed_to_open_session(hass: HomeAssistant) -> None:
    """Raise an API error if a session cannot be opened."""
    coordinator = _create_coordinator(hass)
    coordinator._async_get_session = AsyncMock(return_value=False)  # type: ignore[method-assign]
    with pytest.raises(FreeboxContactApiError):
        await coordinator.async_get_contacts()


async def test_get_contacts_denied_by_session_permissions(hass: HomeAssistant) -> None:
    """Check permissions reported when opening a session."""
    coordinator = _create_coordinator(hass)

    async def _session_without_contacts() -> bool:
        coordinator.session_token = SESSION_TOKEN
        coordinator.permissions = {"contacts": False}
        return True

    coordinator._async_get_session = AsyncMock(side_effect=_session_without_contacts)  # type: ignore[method-assign]
    with pytest.raises(FreeboxContactPermissionError):
        await coordinator.async_get_contacts()


async def test_get_contacts_permission_refresh_still_denied(hass: HomeAssistant) -> None:
    """Refresh stale denied permissions and fail if contacts stay unauthorized."""
    coordinator = _create_coordinator(hass)
    coordinator.session_token = SESSION_TOKEN
    coordinator.permissions = {"contacts": False}

    async def _refresh_without_contacts() -> bool:
        coordinator.session_token = "new-session-token"
        coordinator.permissions = {"contacts": False}
        return True

    coordinator._async_get_session = AsyncMock(side_effect=_refresh_without_contacts)  # type: ignore[method-assign]
    with pytest.raises(FreeboxContactPermissionError):
        await coordinator.async_get_contacts()


async def test_fetch_contacts_requires_session(hass: HomeAssistant) -> None:
    """Reject contact lookup when no session exists."""
    coordinator = _create_coordinator(hass)
    coordinator.session_token = None
    with pytest.raises(FreeboxContactApiError):
        await coordinator._async_fetch_contacts(retry=True)


async def test_fetch_contacts_reports_http_error(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Report an HTTP error instead of returning an empty contact list."""
    coordinator = _create_coordinator(hass)
    aioclient_mock.get(
        f"http://{FREEBOX_HOST}/api/v4/contact/?limit=-1",
        status=500, json={"success": False},
    )
    with pytest.raises(FreeboxContactApiError):
        await coordinator.async_get_contacts()


async def test_fetch_contacts_rejects_invalid_contact_list(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Reject an invalid contacts response result."""
    coordinator = _create_coordinator(hass)
    aioclient_mock.get(
        f"http://{FREEBOX_HOST}/api/v4/contact/?limit=-1",
        json={"success": True, "result": {"not": "a list"}},
    )
    with pytest.raises(FreeboxContactApiError):
        await coordinator.async_get_contacts()


async def test_fetch_contacts_retries_expired_session(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Renew the session and retry when the Freebox rejects the old session."""
    coordinator = _create_coordinator(hass)
    aioclient_mock.get(
        f"http://{FREEBOX_HOST}/api/v4/contact/?limit=-1",
        status=403, json={"success": False, "error_code": "auth_required"},
    )
    aioclient_mock.get(
        f"http://{FREEBOX_HOST}/api/v4/login/",
        json={"success": True, "result": {"challenge": "test-challenge"}},
    )
    aioclient_mock.post(
        f"http://{FREEBOX_HOST}/api/v4/login/session/",
        json={
            "success": True,
            "result": {
                "session_token": "renewed-session-token",
                "permissions": {"contacts": True},
            },
        },
    )
    aioclient_mock.get(
        f"http://{FREEBOX_HOST}/api/v4/contact/?limit=-1",
        json={"success": True, "result": CONTACTS},
    )
    assert await coordinator.async_get_contacts() == CONTACTS
    assert coordinator.session_token == "renewed-session-token"


async def test_fetch_contacts_detects_permission_error_in_json_body(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Detect missing permissions from the Freebox error code in the body."""
    coordinator = _create_coordinator(hass)
    aioclient_mock.get(
        f"http://{FREEBOX_HOST}/api/v4/contact/?limit=-1",
        json={"success": False, "error_code": "insufficient_rights"},
    )
    with pytest.raises(FreeboxContactPermissionError):
        await coordinator.async_get_contacts()


async def test_update_data_session_error_still_raises_update_failed(
    hass: HomeAssistant,
) -> None:
    """Preserve the existing coordinator failure behavior."""
    coordinator = _create_coordinator(hass)
    coordinator._async_get_session = AsyncMock(return_value=False)  # type: ignore[method-assign]
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
