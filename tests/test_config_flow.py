"""Tests for the Freebox Caller ID config flow."""

from __future__ import annotations

import aiohttp
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.freebox_caller_id.config_flow import FreeboxCallerIDConfigFlow
from custom_components.freebox_caller_id.const import (
    CONF_APP_TOKEN,
    CONF_HOST,
    CONF_RINGING_TIMEOUT,
    CONF_SCAN_INTERVAL,
    DEFAULT_HOST,
    DEFAULT_RINGING_TIMEOUT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

FREEBOX_HOST = "192.168.1.254"
FREEBOX_UID = "test-freebox-uid"
APP_TOKEN = "test-app-token"
NEW_APP_TOKEN = "new-test-app-token"
TRACK_ID = "test-track-id"
REAUTH_TRACK_ID = "reauth-track-id"


def _register_freebox_api(
    aioclient_mock,
    *,
    api_version_status: int = 200,
    api_version_json: dict[str, object] | None = None,
    authorize_status: int = 200,
    authorize_json: dict[str, object] | None = None,
    authorization_status: int = 200,
    authorization_json: dict[str, object] | None = None,
) -> None:
    """Register mocked Freebox config-flow endpoints."""
    base_url = f"http://{FREEBOX_HOST}"

    aioclient_mock.get(
        f"{base_url}/api_version",
        status=api_version_status,
        json=(
            api_version_json
            if api_version_json is not None
            else {"uid": FREEBOX_UID}
        ),
    )

    aioclient_mock.post(
        f"{base_url}/api/v4/login/authorize/",
        status=authorize_status,
        json=(
            authorize_json
            if authorize_json is not None
            else {
                "success": True,
                "result": {
                    "app_token": APP_TOKEN,
                    "track_id": TRACK_ID,
                },
            }
        ),
    )

    aioclient_mock.get(
        f"{base_url}/api/v4/login/authorize/{TRACK_ID}",
        status=authorization_status,
        json=(
            authorization_json
            if authorization_json is not None
            else {
                "result": {
                    "status": "granted",
                },
            }
        ),
    )


async def _start_flow(
    hass: HomeAssistant,
) -> dict[str, object]:
    """Start the user config flow."""
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )


async def _submit_host(
    hass: HomeAssistant,
    flow_id: str,
) -> dict[str, object]:
    """Submit the Freebox host."""
    return await hass.config_entries.flow.async_configure(
        flow_id,
        user_input={
            CONF_HOST: FREEBOX_HOST,
        },
    )


def _create_entry() -> MockConfigEntry:
    """Create a configured Freebox entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Freebox Caller ID",
        unique_id=FREEBOX_UID,
        data={
            CONF_HOST: FREEBOX_HOST,
            CONF_APP_TOKEN: APP_TOKEN,
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
        },
    )


async def test_user_flow_success(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test a successful configuration flow."""
    _register_freebox_api(aioclient_mock)

    result = await _start_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await _submit_host(
        hass,
        result["flow_id"],
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "authorize"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Freebox Caller ID"
    assert result["data"] == {
        CONF_HOST: FREEBOX_HOST,
        CONF_APP_TOKEN: APP_TOKEN,
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
    }
    assert result["result"].unique_id == FREEBOX_UID


async def test_user_flow_uses_default_host(
    hass: HomeAssistant,
) -> None:
    """Test that the user form uses the expected default host."""
    result = await _start_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    schema = result["data_schema"].schema

    host_key = next(
        key
        for key in schema
        if getattr(key, "schema", None) == CONF_HOST
    )

    assert host_key.default() == DEFAULT_HOST


async def test_user_flow_cannot_add_second_entry(
    hass: HomeAssistant,
) -> None:
    """Test that only one config entry is allowed."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    result = await _start_flow(hass)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_api_version_http_error(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test an API version HTTP error."""
    _register_freebox_api(
        aioclient_mock,
        api_version_status=500,
    )

    result = await _start_flow(hass)
    result = await _submit_host(hass, result["flow_id"])

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {
        "base": "cannot_connect",
    }


async def test_user_flow_api_version_missing_uid(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test rejection when the Freebox UID is missing."""
    _register_freebox_api(
        aioclient_mock,
        api_version_json={},
    )

    result = await _start_flow(hass)
    result = await _submit_host(hass, result["flow_id"])

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {
        "base": "cannot_connect",
    }


async def test_user_flow_api_version_invalid_json(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test rejection of an invalid API version response."""
    aioclient_mock.get(
        f"http://{FREEBOX_HOST}/api_version",
        status=200,
        text="invalid",
    )

    result = await _start_flow(hass)
    result = await _submit_host(hass, result["flow_id"])

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {
        "base": "cannot_connect",
    }


async def test_user_flow_connection_error(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test a connection failure."""
    aioclient_mock.get(
        f"http://{FREEBOX_HOST}/api_version",
        exc=aiohttp.ClientError,
    )

    result = await _start_flow(hass)
    result = await _submit_host(hass, result["flow_id"])

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {
        "base": "cannot_connect",
    }


async def test_user_flow_authorization_http_error(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test an authorization HTTP failure."""
    _register_freebox_api(
        aioclient_mock,
        authorize_status=500,
    )

    result = await _start_flow(hass)
    result = await _submit_host(hass, result["flow_id"])

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {
        "base": "auth_failed",
    }


async def test_user_flow_authorization_invalid_json(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test an invalid authorization response."""
    base_url = f"http://{FREEBOX_HOST}"

    aioclient_mock.get(
        f"{base_url}/api_version",
        json={"uid": FREEBOX_UID},
    )
    aioclient_mock.post(
        f"{base_url}/api/v4/login/authorize/",
        status=200,
        text="invalid",
    )

    result = await _start_flow(hass)
    result = await _submit_host(hass, result["flow_id"])

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {
        "base": "auth_failed",
    }


async def test_user_flow_authorization_unsuccessful(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test an unsuccessful authorization response."""
    _register_freebox_api(
        aioclient_mock,
        authorize_json={
            "success": False,
            "error_code": "denied",
        },
    )

    result = await _start_flow(hass)
    result = await _submit_host(hass, result["flow_id"])

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {
        "base": "auth_failed",
    }


async def test_user_flow_authorization_connection_error(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test an authorization connection failure."""
    base_url = f"http://{FREEBOX_HOST}"

    aioclient_mock.get(
        f"{base_url}/api_version",
        json={"uid": FREEBOX_UID},
    )
    aioclient_mock.post(
        f"{base_url}/api/v4/login/authorize/",
        exc=aiohttp.ClientError,
    )

    result = await _start_flow(hass)
    result = await _submit_host(hass, result["flow_id"])

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {
        "base": "cannot_connect",
    }


async def test_user_flow_authorization_pending(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test a pending authorization."""
    _register_freebox_api(
        aioclient_mock,
        authorization_json={
            "result": {
                "status": "pending",
            },
        },
    )

    result = await _start_flow(hass)
    result = await _submit_host(hass, result["flow_id"])

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "authorize"
    assert result["errors"] == {
        "base": "pending_auth",
    }


async def test_user_flow_authorization_denied(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test a denied authorization."""
    _register_freebox_api(
        aioclient_mock,
        authorization_json={
            "result": {
                "status": "denied",
            },
        },
    )

    result = await _start_flow(hass)
    result = await _submit_host(hass, result["flow_id"])

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "authorize"
    assert result["errors"] == {
        "base": "auth_denied",
    }


async def test_authorize_connection_error(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test a connection failure while checking authorization."""
    base_url = f"http://{FREEBOX_HOST}"

    aioclient_mock.get(
        f"{base_url}/api_version",
        json={"uid": FREEBOX_UID},
    )
    aioclient_mock.post(
        f"{base_url}/api/v4/login/authorize/",
        json={
            "success": True,
            "result": {
                "app_token": APP_TOKEN,
                "track_id": TRACK_ID,
            },
        },
    )
    aioclient_mock.get(
        f"{base_url}/api/v4/login/authorize/{TRACK_ID}",
        exc=aiohttp.ClientError,
    )

    result = await _start_flow(hass)
    result = await _submit_host(hass, result["flow_id"])

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "authorize"
    assert result["errors"] == {
        "base": "cannot_connect",
    }

async def test_reauth_without_host(
    hass: HomeAssistant,
) -> None:
    """Test that reauth aborts when no host is available."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
        },
        data={},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "auth_failed"


async def test_reauth_api_version_http_error(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test reauth when Freebox API version returns an HTTP error."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    aioclient_mock.get(
        f"http://{FREEBOX_HOST}/api_version",
        status=500,
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": FREEBOX_UID,
        },
        data=entry.data,
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {
        "base": "cannot_connect",
    }


async def test_reauth_api_version_invalid_json(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test reauth with an invalid API version response."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    aioclient_mock.get(
        f"http://{FREEBOX_HOST}/api_version",
        status=200,
        text="invalid",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": FREEBOX_UID,
        },
        data=entry.data,
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {
        "base": "cannot_connect",
    }


async def test_reauth_api_version_missing_uid(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test reauth when the Freebox UID is missing."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    aioclient_mock.get(
        f"http://{FREEBOX_HOST}/api_version",
        json={},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": FREEBOX_UID,
        },
        data=entry.data,
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {
        "base": "cannot_connect",
    }


async def test_reauth_api_version_connection_error(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test reauth when Freebox API version cannot be reached."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    aioclient_mock.get(
        f"http://{FREEBOX_HOST}/api_version",
        exc=aiohttp.ClientError,
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": FREEBOX_UID,
        },
        data=entry.data,
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {
        "base": "cannot_connect",
    }


async def test_reauth_authorization_http_error(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test reauth when authorization returns an HTTP error."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    base_url = f"http://{FREEBOX_HOST}"

    aioclient_mock.get(
        f"{base_url}/api_version",
        json={"uid": FREEBOX_UID},
    )
    aioclient_mock.post(
        f"{base_url}/api/v4/login/authorize/",
        status=500,
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": FREEBOX_UID,
        },
        data=entry.data,
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {
        "base": "auth_failed",
    }


async def test_reauth_authorization_invalid_json(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test reauth with an invalid authorization response."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    base_url = f"http://{FREEBOX_HOST}"

    aioclient_mock.get(
        f"{base_url}/api_version",
        json={"uid": FREEBOX_UID},
    )
    aioclient_mock.post(
        f"{base_url}/api/v4/login/authorize/",
        status=200,
        text="invalid",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": FREEBOX_UID,
        },
        data=entry.data,
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {
        "base": "auth_failed",
    }


async def test_reauth_authorization_unsuccessful(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test reauth with an unsuccessful authorization response."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    base_url = f"http://{FREEBOX_HOST}"

    aioclient_mock.get(
        f"{base_url}/api_version",
        json={"uid": FREEBOX_UID},
    )
    aioclient_mock.post(
        f"{base_url}/api/v4/login/authorize/",
        json={
            "success": False,
            "error_code": "denied",
        },
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": FREEBOX_UID,
        },
        data=entry.data,
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {
        "base": "auth_failed",
    }


async def test_reauth_authorization_connection_error(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test reauth when authorization cannot be requested."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    base_url = f"http://{FREEBOX_HOST}"

    aioclient_mock.get(
        f"{base_url}/api_version",
        json={"uid": FREEBOX_UID},
    )
    aioclient_mock.post(
        f"{base_url}/api/v4/login/authorize/",
        exc=aiohttp.ClientError,
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": FREEBOX_UID,
        },
        data=entry.data,
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {
        "base": "cannot_connect",
    }


async def test_reauth_flow_success(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test successful reauthentication updates the existing entry."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    base_url = f"http://{FREEBOX_HOST}"

    aioclient_mock.get(
        f"{base_url}/api_version",
        json={"uid": FREEBOX_UID},
    )
    aioclient_mock.post(
        f"{base_url}/api/v4/login/authorize/",
        json={
            "success": True,
            "result": {
                "app_token": NEW_APP_TOKEN,
                "track_id": REAUTH_TRACK_ID,
            },
        },
    )
    aioclient_mock.get(
        f"{base_url}/api/v4/login/authorize/{REAUTH_TRACK_ID}",
        json={
            "result": {
                "status": "granted",
            },
        },
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": FREEBOX_UID,
        },
        data=entry.data,
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "authorize"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"

    updated_entry = hass.config_entries.async_get_entry(
        entry.entry_id,
    )

    assert updated_entry is not None
    assert updated_entry.data[CONF_APP_TOKEN] == NEW_APP_TOKEN
    assert updated_entry.data[CONF_HOST] == FREEBOX_HOST
    assert updated_entry.data[CONF_SCAN_INTERVAL] == DEFAULT_SCAN_INTERVAL

    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_reauth_flow_rejects_different_freebox(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test that reauthentication cannot target another Freebox."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    aioclient_mock.get(
        f"http://{FREEBOX_HOST}/api_version",
        json={"uid": "another-freebox-uid"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": FREEBOX_UID,
        },
        data=entry.data,
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"


async def test_reauth_flow_connection_error(
    hass: HomeAssistant,
    aioclient_mock,
) -> None:
    """Test a connection failure during reauthentication."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    aioclient_mock.get(
        f"http://{FREEBOX_HOST}/api_version",
        exc=aiohttp.ClientError,
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "unique_id": FREEBOX_UID,
        },
        data=entry.data,
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {
        "base": "cannot_connect",
    }


async def test_options_flow_defaults(
    hass: HomeAssistant,
) -> None:
    """Test the default options."""
    entry = _create_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(
        entry.entry_id,
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL + 1,
            CONF_RINGING_TIMEOUT: DEFAULT_RINGING_TIMEOUT + 5,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL + 1,
        CONF_RINGING_TIMEOUT: DEFAULT_RINGING_TIMEOUT + 5,
    }


async def test_options_flow_reads_values_from_entry_data(
    hass: HomeAssistant,
) -> None:
    """Test that options fall back to config entry data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Freebox Caller ID",
        unique_id=FREEBOX_UID,
        data={
            CONF_HOST: FREEBOX_HOST,
            CONF_APP_TOKEN: APP_TOKEN,
            CONF_SCAN_INTERVAL: 10,
        },
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(
        entry.entry_id,
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
