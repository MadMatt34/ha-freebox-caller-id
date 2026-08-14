"""Config flow pour l'intégration Freebox Caller ID."""

from __future__ import annotations

import logging
from typing import cast

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

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
    FreeboxAuthorizeResponse,
    FreeboxAuthorizationStatusResponse,
    FreeboxConfigData,
    FreeboxOptionsData,
    FreeboxUserInput,
)

_LOGGER = logging.getLogger(__name__)


class FreeboxCallerIDConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    """Gère le flux de configuration UI pour Freebox Caller ID."""

    VERSION = 1

    host: str | None
    app_token: str | None
    track_id: str | None

    def __init__(self) -> None:
        """Initialisation."""
        self.host = None
        self.app_token = None
        self.track_id = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> FreeboxCallerIDOptionsFlow:
        """Dit à Home Assistant qu'un menu d'options existe."""
        return FreeboxCallerIDOptionsFlow(config_entry)

    async def async_step_user(
        self,
        user_input: dict[str, object] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Étape 1 : demander l'adresse de la Freebox."""
        errors: dict[str, str] = {}

        if user_input is not None:
            input_data = cast(
                FreeboxUserInput,
                user_input,
            )

            self.host = input_data[CONF_HOST].strip()

            session = async_get_clientsession(self.hass)

            fb_uid: str | None = None

            try:
                async with session.get(
                    f"http://{self.host}/api_version",
                    timeout=5,
                ) as resp_ver:
                    if resp_ver.status == 200:
                        ver_data = await resp_ver.json()

                        if isinstance(ver_data, dict):
                            uid = ver_data.get("uid")

                            if isinstance(uid, str):
                                fb_uid = uid

            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "Impossible d'extraire l'UID de la Freebox (%s), poursuite...",
                    err,
                )

            if fb_uid:
                await self.async_set_unique_id(fb_uid)
                self._abort_if_unique_id_configured()

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
                ) as resp:
                    raw_data = await resp.json()

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

            except Exception as err:  # noqa: BLE001
                _LOGGER.error(
                    "Erreur de connexion à la Freebox: %s",
                    err,
                )
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST,
                        default=DEFAULT_HOST,
                    ): str,
                }
            ),
            errors=errors,
        )

    async def async_step_authorize(
        self,
        user_input: dict[str, object] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Étape 2 : attendre l'autorisation sur la Freebox."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if self.host is None or self.track_id is None:
                return self.async_abort(reason="auth_failed")

            session = async_get_clientsession(self.hass)

            status: str | None = None

            try:
                async with session.get(
                    f"http://{self.host}/api/v4/login/authorize/"
                    f"{self.track_id}"
                ) as resp:
                    raw_data = await resp.json()

                    if isinstance(raw_data, dict):
                        data = cast(
                            FreeboxAuthorizationStatusResponse,
                            raw_data,
                        )
                        status = data["result"]["status"]

            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"

            if status == "granted":
                if not self.unique_id:
                    await self.async_set_unique_id(
                        self.host.lower()
                    )
                    self._abort_if_unique_id_configured()

                if self.app_token is None:
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
            description_placeholders={"host": self.host or ""},
        )


class FreeboxCallerIDOptionsFlow(config_entries.OptionsFlow):
    """Gère les options via le bouton Configurer de l'UI."""

    def __init__(
        self,
        config_entry: config_entries.ConfigEntry,
    ) -> None:
        """Initialise le flow d'options."""
        self.config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, object] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Gère les options."""
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
