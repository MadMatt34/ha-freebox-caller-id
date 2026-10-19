"""On-demand contact lookup actions for Freebox Caller ID."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import cast

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryAuthFailed,
    ConfigEntryState,
)
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import (
    FreeboxCallerCoordinator,
    FreeboxContactApiError,
    FreeboxContactPermissionError,
)
from .types import (
    FreeboxContact,
    FreeboxContactLookupResponse,
    FreeboxContactNumberResult,
    FreeboxContactResult,
)

SERVICE_CONTACT_BY_NUMBER = "contact_by_number"
SERVICE_CONTACT_BY_NAME = "contact_by_name"

_PHONE_FORMATTING = re.compile(r"[\s().-]+")

_CONTACT_BY_NUMBER_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry_id"): cv.string,
        vol.Required("phone_number"): cv.string,
    }
)
_CONTACT_BY_NAME_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry_id"): cv.string,
        vol.Required("name"): cv.string,
    }
)


def _normalize_phone_number(number: str) -> str:
    """Remove common formatting characters without changing country codes."""
    return _PHONE_FORMATTING.sub("", number).strip()


def _contact_result(
    contact: FreeboxContact,
    *,
    matched_number: str | None = None,
) -> FreeboxContactResult:
    """Return only supported, JSON-safe contact fields."""
    result: FreeboxContactResult = {}

    contact_id = contact.get("id")
    if isinstance(contact_id, int):
        result["id"] = contact_id

    for key in ("display_name", "first_name", "last_name", "company"):
        value = contact.get(key)
        if isinstance(value, str) and value:
            result[key] = value

    if matched_number is not None:
        result["matched_number"] = matched_number

    raw_numbers = contact.get("numbers", [])
    numbers: list[FreeboxContactNumberResult] = []
    if isinstance(raw_numbers, list):
        for raw_number in raw_numbers:
            if not isinstance(raw_number, Mapping):
                continue
            number_value = raw_number.get("number")
            if not isinstance(number_value, str) or not number_value:
                continue

            number_result: FreeboxContactNumberResult = {"number": number_value}
            for key in ("type", "label"):
                value = raw_number.get(key)
                if isinstance(value, str) and value:
                    number_result[key] = value
            numbers.append(number_result)

    if numbers:
        result["numbers"] = numbers

    return result


def _find_contacts_by_number(
    contacts: list[FreeboxContact],
    phone_number: str,
) -> list[FreeboxContactResult]:
    """Find contacts by an exact number match, ignoring formatting."""
    searched_number = _normalize_phone_number(phone_number)
    matches: list[FreeboxContactResult] = []

    for contact in contacts:
        raw_numbers = contact.get("numbers", [])
        if not isinstance(raw_numbers, list):
            continue
        for item in raw_numbers:
            if not isinstance(item, Mapping):
                continue
            number = item.get("number")
            if (
                isinstance(number, str)
                and _normalize_phone_number(number) == searched_number
            ):
                matches.append(_contact_result(contact, matched_number=number))
                break

    return matches


def _find_contacts_by_name(
    contacts: list[FreeboxContact],
    name: str,
) -> list[FreeboxContactResult]:
    """Find contacts by case-insensitive substring in their name fields."""
    searched_name = name.casefold()
    matches: list[FreeboxContactResult] = []

    for contact in contacts:
        first_name = contact.get("first_name") or ""
        last_name = contact.get("last_name") or ""
        values = (
            contact.get("display_name", ""),
            first_name,
            last_name,
            contact.get("company", ""),
            f"{first_name} {last_name}".strip(),
        )
        if any(
            isinstance(value, str) and searched_name in value.casefold()
            for value in values
        ):
            matches.append(_contact_result(contact))

    return matches


def _get_coordinator(
    hass: HomeAssistant,
    config_entry_id: str,
) -> FreeboxCallerCoordinator:
    """Return the coordinator for a loaded Freebox Caller ID entry."""
    entry = hass.config_entries.async_get_entry(config_entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="config_entry_not_found",
        )

    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="config_entry_not_loaded",
        )

    return cast(ConfigEntry[FreeboxCallerCoordinator], entry).runtime_data


def _translate_contact_error(err: Exception) -> HomeAssistantError:
    """Convert contact API failures to translated action errors."""
    if isinstance(err, FreeboxContactPermissionError):
        return HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="contacts_permission_denied",
        )
    if isinstance(err, FreeboxContactApiError):
        return HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="contact_lookup_failed",
        )
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="invalid_app_token",
    )


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration actions."""
    async def async_contact_by_number(call: ServiceCall) -> ServiceResponse:
        """Find a contact by phone number."""
        phone_number = call.data["phone_number"].strip()
        if not phone_number:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="empty_phone_number",
            )

        coordinator = _get_coordinator(hass, call.data["config_entry_id"])
        try:
            contacts = await coordinator.async_get_contacts()
        except (
            FreeboxContactPermissionError,
            FreeboxContactApiError,
            ConfigEntryAuthFailed,
        ) as err:
            raise _translate_contact_error(err) from err

        response: FreeboxContactLookupResponse = {
            "matches": _find_contacts_by_number(contacts, phone_number),
        }
        return response

    async def async_contact_by_name(call: ServiceCall) -> ServiceResponse:
        """Find a contact by name."""
        name = call.data["name"].strip()
        if not name:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="empty_contact_name",
            )

        coordinator = _get_coordinator(hass, call.data["config_entry_id"])
        try:
            contacts = await coordinator.async_get_contacts()
        except (
            FreeboxContactPermissionError,
            FreeboxContactApiError,
            ConfigEntryAuthFailed,
        ) as err:
            raise _translate_contact_error(err) from err

        response: FreeboxContactLookupResponse = {
            "matches": _find_contacts_by_name(contacts, name),
        }
        return response

    hass.services.async_register(
        DOMAIN,
        SERVICE_CONTACT_BY_NUMBER,
        async_contact_by_number,
        schema=_CONTACT_BY_NUMBER_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CONTACT_BY_NAME,
        async_contact_by_name,
        schema=_CONTACT_BY_NAME_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
