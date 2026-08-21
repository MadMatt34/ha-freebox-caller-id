"""Support des diagnostics pour Freebox Caller ID."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import FreeboxConfigEntry
from .const import CONF_APP_TOKEN, CONF_HOST

TO_REDACT = {
    CONF_APP_TOKEN,
    CONF_HOST,
    "app_token",
    "session_token",
    "caller_number",
    "caller_name",
    "number",
    "name",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: FreeboxConfigEntry,
) -> dict[str, Any]:
    """Retourne les données de diagnostic masquées et sécurisées."""
    coordinator = entry.runtime_data
    raw_data = coordinator.data or {}

    sanitized_data = async_redact_data(
        raw_data,
        TO_REDACT,
    )

    if isinstance(sanitized_data, dict) and "recent_calls" in sanitized_data:
        sanitized_data["recent_calls"] = [
            async_redact_data(call, TO_REDACT) if isinstance(call, dict) else call
            for call in sanitized_data.get("recent_calls", [])
        ]

    return {
        "entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "data": async_redact_data(
                dict(entry.data),
                TO_REDACT,
            ),
            "options": dict(entry.options),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": (
                str(coordinator.update_interval) if coordinator.update_interval else None
            ),
            "data": sanitized_data,
        },
    }
