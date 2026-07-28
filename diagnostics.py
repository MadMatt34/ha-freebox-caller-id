"""Support des diagnostics pour Freebox Caller ID."""
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_APP_TOKEN, DOMAIN

TO_REDACT = {CONF_APP_TOKEN, "session_token"}

async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry):
    """Retourne les données de diagnostic masquées."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "coordinator_data": async_redact_data(coordinator.data, TO_REDACT),
    }
