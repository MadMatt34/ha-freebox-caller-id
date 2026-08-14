"""Intégration Custom Freebox Caller ID pour Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_APP_TOKEN,
    CONF_HOST,
    CONF_RINGING_TIMEOUT,
    CONF_SCAN_INTERVAL,
    DEFAULT_RINGING_TIMEOUT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import FreeboxCallerCoordinator


type FreeboxConfigEntry = ConfigEntry[FreeboxCallerCoordinator]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FreeboxConfigEntry,
) -> bool:
    """Initialisation du composant via l'interface UI."""
    host = entry.data[CONF_HOST]
    app_token = entry.data[CONF_APP_TOKEN]

    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(
            CONF_SCAN_INTERVAL,
            DEFAULT_SCAN_INTERVAL,
        ),
    )

    ringing_timeout = entry.options.get(
        CONF_RINGING_TIMEOUT,
        entry.data.get(
            CONF_RINGING_TIMEOUT,
            DEFAULT_RINGING_TIMEOUT,
        ),
    )

    session = async_get_clientsession(hass)

    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=session,
        host=host,
        app_token=app_token,
        scan_interval=scan_interval,
        ringing_timeout=ringing_timeout,
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(
        entry,
        PLATFORMS,
    )

    entry.async_on_unload(
        entry.add_update_listener(async_reload_entry)
    )

    return True


async def async_reload_entry(
    hass: HomeAssistant,
    entry: FreeboxConfigEntry,
) -> None:
    """Recharge l'intégration si les options sont modifiées."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant,
    entry: FreeboxConfigEntry,
) -> bool:
    """Désinstallation de l'intégration."""
    return await hass.config_entries.async_unload_platforms(
        entry,
        PLATFORMS,
    )
