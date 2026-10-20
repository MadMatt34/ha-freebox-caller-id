"""On-demand contact lookup actions for Freebox Caller ID."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import cast

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
import phonenumbers
import voluptuous as vol

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
MIN_SEARCH_LENGTH = 3


def _phone_search_error(phone_number: str) -> str | None:
    """Return the validation error key for a phone-number search, if any."""
    if not re.fullmatch(r"\+?[0-9]+", phone_number):
        return "invalid_phone_number"
    if sum("0" <= character <= "9" for character in phone_number) < MIN_SEARCH_LENGTH:
        return "search_too_short"
    return None


def _has_explicit_international_prefix(number: str) -> bool:
    """Return whether a number explicitly starts with an international prefix."""
    normalized_number = number.strip()
    return normalized_number.startswith("+") or normalized_number.startswith("00")


def _phone_country_code(
    number: str,
    *,
    assume_french_national: bool = False,
) -> int | None:
    """Return a known country calling code without guessing for search fragments."""
    normalized_number = number.strip()
    has_explicit_prefix = _has_explicit_international_prefix(normalized_number)
    if not has_explicit_prefix and not assume_french_national:
        return None

    default_region = "FR" if normalized_number.startswith("00") or assume_french_national else None
    try:
        parsed_number = phonenumbers.parse(normalized_number, default_region)
    except phonenumbers.NumberParseException:
        return None

    # A stored national number is treated as French only when it resembles a
    # complete phone number. Short fragments must never acquire a country code.
    if not has_explicit_prefix and not phonenumbers.is_possible_number(parsed_number):
        return None

    return parsed_number.country_code


def _phone_number_variants(
    number: str,
    *,
    assume_french_national: bool = False,
) -> set[str]:
    """Return digit-only variants without assigning a country to search fragments.

    Explicit international prefixes are parsed directly. Stored national-format
    contact numbers may be normalized as French full numbers so they can match
    an explicit international query or its national representation.
    """
    normalized_number = number.strip()
    digits = re.sub(r"\D", "", normalized_number)
    if not digits:
        return set()

    variants = {digits}
    has_explicit_prefix = _has_explicit_international_prefix(normalized_number)
    if not has_explicit_prefix and not assume_french_national:
        return variants

    default_region = "FR" if normalized_number.startswith("00") or assume_french_national else None
    try:
        parsed_number = phonenumbers.parse(normalized_number, default_region)
    except phonenumbers.NumberParseException:
        return variants

    # Do not normalize an incomplete stored number by assuming it is French.
    if (
        assume_french_national
        and not has_explicit_prefix
        and not phonenumbers.is_possible_number(parsed_number)
    ):
        return variants

    national_significant_number = phonenumbers.national_significant_number(parsed_number)
    if national_significant_number:
        variants.add(national_significant_number)
        if parsed_number.country_code == 33:
            variants.add(f"0{national_significant_number}")

    if not phonenumbers.is_possible_number(parsed_number):
        return variants

    for number_format in (
        phonenumbers.PhoneNumberFormat.E164,
        phonenumbers.PhoneNumberFormat.NATIONAL,
    ):
        formatted_number = phonenumbers.format_number(
            parsed_number,
            number_format,
        )
        formatted_digits = re.sub(r"\D", "", formatted_number)
        if formatted_digits:
            variants.add(formatted_digits)

    return variants


_CONTACT_BY_NUMBER_SCHEMA = vol.Schema(
    {
        vol.Required("phone_number"): cv.string,
    }
)
_CONTACT_BY_NAME_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
    }
)


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
    """Find contacts by a full number or any digit sequence."""
    if _phone_search_error(phone_number) is not None:
        return []

    searched_variants = _phone_number_variants(phone_number)
    if not searched_variants:
        return []

    # Only an explicit international prefix on the query constrains the country.
    searched_country = _phone_country_code(phone_number)
    matches: list[FreeboxContactResult] = []

    for contact in contacts:
        raw_numbers = contact.get("numbers", [])
        if not isinstance(raw_numbers, list):
            continue
        for item in raw_numbers:
            if not isinstance(item, Mapping):
                continue
            number = item.get("number")
            if not isinstance(number, str) or not number:
                continue

            # Do not match coincidentally similar digits across different countries.
            contact_country = _phone_country_code(
                number,
                assume_french_national=True,
            )
            if (
                searched_country is not None
                and contact_country is not None
                and searched_country != contact_country
            ):
                continue

            contact_variants = _phone_number_variants(
                number,
                assume_french_national=True,
            )
            if any(
                searched in candidate
                for searched in searched_variants
                for candidate in contact_variants
            ):
                matches.append(_contact_result(contact, matched_number=number))
                break

    return matches


def _find_contacts_by_name(
    contacts: list[FreeboxContact],
    name: str,
) -> list[FreeboxContactResult]:
    """Find contacts by case-insensitive substring in their name fields."""
    searched_name = name.strip()
    if len(searched_name) < MIN_SEARCH_LENGTH:
        return []
    searched_name = searched_name.casefold()
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
        if any(isinstance(value, str) and searched_name in value.casefold() for value in values):
            matches.append(_contact_result(contact))

    return matches


def _get_coordinator(hass: HomeAssistant) -> FreeboxCallerCoordinator:
    """Return the coordinator for the single configured Freebox Caller ID entry."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="config_entry_not_found",
        )

    entry = entries[0]
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
        phone_number = call.data["phone_number"]
        if not phone_number.strip():
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="empty_phone_number",
            )

        validation_error = _phone_search_error(phone_number)
        if validation_error == "search_too_short":
            # Never query the Freebox for a search shorter than the minimum.
            response: FreeboxContactLookupResponse = {"matches": []}
            return response
        if validation_error is not None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key=validation_error,
            )

        coordinator = _get_coordinator(hass)
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

        if len(name) < MIN_SEARCH_LENGTH:
            # Never query the Freebox for a search shorter than the minimum.
            response: FreeboxContactLookupResponse = {"matches": []}
            return response

        coordinator = _get_coordinator(hass)
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
