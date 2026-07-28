"""Config flow pour l'intégration Freebox Caller ID."""
from __future__ import annotations

import logging

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
    CONF_SCAN_INTERVAL,
    DEFAULT_HOST,
    DEFAULT_SCAN_INTERVAL,
    DEVICE_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

class FreeboxCallerIDConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Gère le flux de configuration UI pour Freebox Caller ID."""
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Dit à Home Assistant qu'un menu d'options existe."""
        return FreeboxCallerIDOptionsFlow()

    def __init__(self):
        """Initialisation."""
        self.host = None
        self.app_token = None
        self.track_id = None

    async def async_step_user(self, user_input=None):
        """Étape 1 : Demander l'adresse de la Freebox et vérifier les doublons."""
        errors = {}

        if user_input is not None:
            self.host = user_input[CONF_HOST].strip()
            session = async_get_clientsession(self.hass)

            # 1. Récupération de l'UID (dans son propre bloc try/except)
            fb_uid = None
            try:
                async with session.get(f"http://{self.host}/api_version", timeout=5) as resp_ver:
                    if resp_ver.status == 200:
                        ver_data = await resp_ver.json()
                        fb_uid = ver_data.get("uid")
            except Exception as e:    # noqa: BLE001
                _LOGGER.warning("Impossible d'extraire l'UID de la Freebox (%s), poursuite...", e)

            # 2. Vérification d'unicité HORS du try/except
            if fb_uid:
                await self.async_set_unique_id(fb_uid)
                self._abort_if_unique_id_configured()

            # 3. Demande d'autorisation à la Freebox
            payload = {
                "app_id": APP_ID,
                "app_name": APP_NAME,
                "app_version": APP_VERSION,
                "device_name": DEVICE_NAME
            }
            try:
                async with session.post(f"http://{self.host}/api/v4/login/authorize/", json=payload) as resp:
                    data = await resp.json()
                    if data.get("success"):
                        self.app_token = data["result"]["app_token"]
                        self.track_id = data["result"]["track_id"]
                        return await self.async_step_authorize()
                    else:
                        errors["base"] = "auth_failed"
            except Exception as e:    # noqa: BLE001
                _LOGGER.error("Erreur de connexion à la Freebox: %s", e)
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
            }),
            errors=errors,
        )

    async def async_step_authorize(self, user_input=None):
        """Étape 2 : Attendre que l'utilisateur valide sur l'écran de la Freebox."""
        errors = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            status = None
            
            try:
                async with session.get(f"http://{self.host}/api/v4/login/authorize/{self.track_id}") as resp:
                    data = await resp.json()
                    status = data["result"]["status"]
            except Exception:    # noqa: BLE001
                errors["base"] = "cannot_connect"

            if status == "granted":
                # Secours : Si l'UID n'a pas pu être récupéré à l'étape 1
                if not self.unique_id:
                    await self.async_set_unique_id(self.host.lower())
                    self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="Freebox Caller ID", 
                    data={
                        CONF_HOST: self.host,
                        CONF_APP_TOKEN: self.app_token,
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL
                    }
                )
            elif status == "pending":
                errors["base"] = "pending_auth"
            elif status is not None:
                errors["base"] = "auth_denied"

        return self.async_show_form(
            step_id="authorize",
            errors=errors,
            description_placeholders={"host": self.host}
        )


class FreeboxCallerIDOptionsFlow(config_entries.OptionsFlow):
    """Gère les options via le bouton Configurer de l'UI."""

    async def async_step_init(self, user_input=None):
        """Gère le formulaire des options sous forme de champ numérique."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, 
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_SCAN_INTERVAL, default=current_interval): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=60,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                )
            })
        )
