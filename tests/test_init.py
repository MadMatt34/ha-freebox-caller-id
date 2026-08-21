"""Tests for the Freebox Caller ID integration setup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryNotReady
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.freebox_caller_id import (
    async_reload_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.freebox_caller_id.const import (
    CONF_APP_TOKEN,
    CONF_HOST,
    CONF_RINGING_TIMEOUT,
    CONF_SCAN_INTERVAL,
    DEFAULT_RINGING_TIMEOUT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)

FREEBOX_HOST = "192.168.1.254"
APP_TOKEN = "test-app-token"


def _create_entry(
    *,
    options: dict[str, int] | None = None,
) -> MockConfigEntry:
    """Create a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Freebox Caller ID",
        unique_id="test-freebox-uid",
        version=1,
        data={
            CONF_HOST: FREEBOX_HOST,
            CONF_APP_TOKEN: APP_TOKEN,
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            CONF_RINGING_TIMEOUT: DEFAULT_RINGING_TIMEOUT,
        },
        options=options or {},
    )


def _create_coordinator() -> MagicMock:
    """Create a coordinator mock."""
    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    return coordinator


async def test_async_setup_entry_success(
    hass: HomeAssistant,
) -> None:
    """Test successful config entry setup."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    coordinator = _create_coordinator()

    with (
        patch(
            "custom_components.freebox_caller_id.FreeboxCallerCoordinator",
            return_value=coordinator,
        ) as coordinator_class,
        patch(
            "custom_components.freebox_caller_id.async_get_clientsession",
        ) as get_session,
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(),
        ) as forward_setups,
    ):
        result = await async_setup_entry(hass, entry)

    assert result is True

    coordinator_class.assert_called_once()
    get_session.assert_called_once_with(hass)
    coordinator.async_config_entry_first_refresh.assert_awaited_once()
    forward_setups.assert_awaited_once_with(
        entry,
        PLATFORMS,
    )
    assert entry.runtime_data is coordinator


async def test_async_setup_entry_uses_options(
    hass: HomeAssistant,
) -> None:
    """Test that configured options override entry data."""
    entry = _create_entry(
        options={
            CONF_SCAN_INTERVAL: 10,
            CONF_RINGING_TIMEOUT: 60,
        },
    )
    entry.add_to_hass(hass)

    coordinator = _create_coordinator()

    with (
        patch(
            "custom_components.freebox_caller_id.FreeboxCallerCoordinator",
            return_value=coordinator,
        ) as coordinator_class,
        patch(
            "custom_components.freebox_caller_id.async_get_clientsession",
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(),
        ),
    ):
        result = await async_setup_entry(hass, entry)

    assert result is True

    call = coordinator_class.call_args.kwargs

    assert call["host"] == FREEBOX_HOST
    assert call["app_token"] == APP_TOKEN
    assert call["entry_id"] == entry.entry_id
    assert call["scan_interval"] == 10
    assert call["ringing_timeout"] == 60


async def test_async_setup_entry_uses_data_defaults(
    hass: HomeAssistant,
) -> None:
    """Test that entry data is used when options are absent."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    coordinator = _create_coordinator()

    with (
        patch(
            "custom_components.freebox_caller_id.FreeboxCallerCoordinator",
            return_value=coordinator,
        ) as coordinator_class,
        patch(
            "custom_components.freebox_caller_id.async_get_clientsession",
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(),
        ),
    ):
        result = await async_setup_entry(hass, entry)

    assert result is True

    call = coordinator_class.call_args.kwargs

    assert call["scan_interval"] == DEFAULT_SCAN_INTERVAL
    assert call["ringing_timeout"] == DEFAULT_RINGING_TIMEOUT


async def test_async_setup_entry_propagates_config_entry_not_ready(
    hass: HomeAssistant,
) -> None:
    """Test initial coordinator failure."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    coordinator = _create_coordinator()
    coordinator.async_config_entry_first_refresh.side_effect = ConfigEntryNotReady

    with (
        patch(
            "custom_components.freebox_caller_id.FreeboxCallerCoordinator",
            return_value=coordinator,
        ),
        patch(
            "custom_components.freebox_caller_id.async_get_clientsession",
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(),
        ) as forward_setups,
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, entry)

    assert entry.runtime_data is None
    forward_setups.assert_not_awaited()


async def test_async_reload_entry(
    hass: HomeAssistant,
) -> None:
    """Test integration reload callback."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    with patch.object(
        hass.config_entries,
        "async_reload",
        new=AsyncMock(),
    ) as reload_entry:
        await async_reload_entry(hass, entry)

    reload_entry.assert_awaited_once_with(entry.entry_id)


async def test_async_unload_entry(
    hass: HomeAssistant,
) -> None:
    """Test unloading the integration."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        new=AsyncMock(return_value=True),
    ) as unload_platforms:
        result = await async_unload_entry(hass, entry)

    assert result is True
    unload_platforms.assert_awaited_once_with(
        entry,
        PLATFORMS,
    )
