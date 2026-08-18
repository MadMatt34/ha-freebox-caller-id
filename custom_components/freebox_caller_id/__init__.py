"""Freebox Caller ID integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_APP_TOKEN,
    CONF_AREA,
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
    """Set up the Freebox Caller ID integration."""
    host = entry.data[CONF_HOST]
    app_token = entry.data[CONF_APP_TOKEN]

    area_id = entry.data.get(CONF_AREA)

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

    coordinator = FreeboxCallerCoordinator(
        hass=hass,
        session=async_get_clientsession(hass),
        host=host,
        app_token=app_token,
        entry_id=entry.entry_id,
        scan_interval=scan_interval,
        ringing_timeout=ringing_timeout,
    )

    # Use Home Assistant's native ConfigEntryNotReady handling.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    # The area is explicitly selected by the user during the config flow.
    # Apply it to the Device Registry before creating the entities so that
    # Home Assistant can use the area when generating new entity IDs.
    if area_id:
        device_registry = dr.async_get(hass)
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, entry.entry_id)},
        )

        if device is not None and device.area_id is None:
            device_registry.async_update_device(
                device.id,
                area_id=area_id,
            )

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
    """Reload the integration after options have changed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant,
    entry: FreeboxConfigEntry,
) -> bool:
    """Unload the integration."""
    return await hass.config_entries.async_unload_platforms(
        entry,
        PLATFORMS,
    )
