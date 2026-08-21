"""Config flow for the Freebox Caller ID integration."""

from __future__ import annotations

import logging
from typing import cast

import aiohttp
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .const import (
    APP_ID,
    APP_NAME,
    APP_VERSION,
    CONF_APP_TOKEN,
    CONF_HOST,
    CONF_RINGING_TIMEOUT,
    CONF_SCAN_INTERVAL,
    DEFAULT_HOST,
    DEFAULT_RINGING_TIMEOUT,
    DEFAULT_SCAN_INTERVAL,
    DEVICE_NAME,
    DOMAIN,
)
from .types import (
    FreeboxAuthorizationStatusResponse,
    FreeboxAuthorizeResponse,
    FreeboxConfigData,
    FreeboxOptionsData,
    FreeboxUserInput,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 5
PARALLEL_UPDATES = 0


class FreeboxCallerIDConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    """Handle the Freebox Caller ID configuration flow"""

    VERSION = 1

    host: str | None
    app_token: str | None
    track_id: str | None

    def __init__(self) -> None:
        """Initialize the configuration flow."""
        self.host = None
        self.app_token = None
        self.track_id = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> FreeboxCallerIDOptionsFlow:
        """Return the options flow."""
        return FreeboxCallerIDOptionsFlow()

    async def async_step_user(
        self,
        user_input: dict[str, object] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial user step."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        errors: dict[str, str] = {}

        if user_input is not None:
            input_data = cast(
                FreeboxUserInput,
                user_input,
            )

            self.host = input_data[CONF_HOST].strip()

            session = async_get_clientsession(self.hass)

            try:
                async with session.get(
                    f"http://{self.host}/api_version",
                    timeout=REQUEST_TIMEOUT,
                ) as response:
                    if response.status != 200:
                        errors["base"] = "cannot_connect"
                    else:
                        raw_data = await response.json()

                        if not isinstance(raw_data, dict):
                            errors["base"] = "cannot_connect"
                        else:
                            uid = raw_data.get("uid")

                            if not isinstance(uid, str) or not uid:
                                errors["base"] = "cannot_connect"
                            else:
                                await self.async_set_unique_id(uid)
                                self._abort_if_unique_id_configured()

            except (
                aiohttp.ClientError,
                TimeoutError,
                ValueError,
            ) as err:
                _LOGGER.warning(
                    "Unable to retrieve Freebox information: %s",
                    err,
                )
                errors["base"] = "cannot_connect"

            if not errors:
                payload = {
                    "app_id": APP_ID,
                    "app_name": APP_NAME,
                    "app_version": APP_VERSION,
                    "device_name": DEVICE_NAME,
                }

                try:
                    async with session.post(
                        f"http://{self.host}/api/v4/login/authorize/",
                        json=payload,
                        timeout=REQUEST_TIMEOUT,
                    ) as response:
                        if response.status != 200:
                            errors["base"] = "auth_failed"
                        else:
                            raw_data = await response.json()

                            if not isinstance(raw_data, dict):
                                errors["base"] = "auth_failed"
                            else:
                                data = cast(
                                    FreeboxAuthorizeResponse,
                                    raw_data,
                                )

                                if data["success"]:
                                    self.app_token = data["result"]["app_token"]
                                    self.track_id = data["result"]["track_id"]

                                    return await self.async_step_authorize()

                                errors["base"] = "auth_failed"

                except (
                    aiohttp.ClientError,
                    TimeoutError,
                    ValueError,
                ) as err:
                    _LOGGER.error(
                        "Error connecting to the Freebox: %s",
                        err,
                    )
                    errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST,
                        default=self.host or DEFAULT_HOST,
                    ): str,
                }
            ),
            errors=errors,
        )

    async def async_step_authorize(
        self,
        user_input: dict[str, object] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Wait for authorization on the Freebox."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if self.host is None or self.track_id is None:
                return self.async_abort(reason="auth_failed")

            session = async_get_clientsession(self.hass)

            status: str | None = None

            try:
                async with session.get(
                    f"http://{self.host}/api/v4/login/authorize/{self.track_id}",
                    timeout=REQUEST_TIMEOUT,
                ) as response:
                    if response.status != 200:
                        errors["base"] = "cannot_connect"
                    else:
                        raw_data = await response.json()

                        if isinstance(raw_data, dict):
                            data = cast(
                                FreeboxAuthorizationStatusResponse,
                                raw_data,
                            )
                            status = data["result"]["status"]
                        else:
                            errors["base"] = "cannot_connect"

            except (
                aiohttp.ClientError,
                TimeoutError,
                ValueError,
            ) as err:
                _LOGGER.warning(
                    "Unable to retrieve authorization status: %s",
                    err,
                )
                errors["base"] = "cannot_connect"

            if status == "granted":
                if self.app_token is None:
                    return self.async_abort(reason="auth_failed")

                if self.unique_id is None:
                    return self.async_abort(reason="auth_failed")

                entry_data: FreeboxConfigData = {
                    CONF_HOST: self.host,
                    CONF_APP_TOKEN: self.app_token,
                    CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                }

                return self.async_create_entry(
                    title="Freebox Caller ID",
                    data=entry_data,
                )

            if status == "pending":
                errors["base"] = "pending_auth"
            elif status is not None:
                errors["base"] = "auth_denied"

        return self.async_show_form(
            step_id="authorize",
            errors=errors,
            description_placeholders={
                "host": self.host or "",
            },
        )


class FreeboxCallerIDOptionsFlow(config_entries.OptionsFlow):
    """Handle the integration options."""

    async def async_step_init(
        self,
        user_input: dict[str, object] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the options."""
        if user_input is not None:
            options_data = cast(
                FreeboxOptionsData,
                user_input,
            )

            return self.async_create_entry(
                title="",
                data=options_data,
            )

        scan_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(
                CONF_SCAN_INTERVAL,
                DEFAULT_SCAN_INTERVAL,
            ),
        )

        ringing_timeout = self.config_entry.options.get(
            CONF_RINGING_TIMEOUT,
            self.config_entry.data.get(
                CONF_RINGING_TIMEOUT,
                DEFAULT_RINGING_TIMEOUT,
            ),
        )

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=scan_interval,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=60,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_RINGING_TIMEOUT,
                    default=ringing_timeout,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=180,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
        )
