"""Config flow pour l'intégration Freebox Caller ID."""
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN, DEFAULT_HOST, APP_ID, APP_NAME, 
    APP_VERSION, DEVICE_NAME, CONF_HOST, CONF_APP_TOKEN, 
    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
)

_LOGGER = logging.getLogger(__name__)

class FreeboxCallerIDConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Gère le flux de configuration UI pour Freebox Caller ID."""
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Dit à Home Assistant qu'un menu d'options existe."""
        return FreeboxCallerIDOptionsFlow(config_entry)

    def __init__(self):
        """Initialisation."""
        self.host = None
        self.app_token = None
        self.track_id = None

    async def async_step_user(self, user_input=None):
        """Étape 1 : Demander l'adresse de la Freebox."""
        errors = {}

        if user_input is not None:
            self.host = user_input[CONF_HOST]
            session = async_get_clientsession(self.hass)
            
            # Demande d'autorisation à la Freebox
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
            except Exception as e:
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
            try:
                # Vérification du statut d'autorisation
                async with session.get(f"http://{self.host}/api/v4/login/authorize/{self.track_id}") as resp:
                    data = await resp.json()
                    status = data["result"]["status"]

                    if status == "granted":
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
                    else:
                        errors["base"] = "auth_denied"
            except Exception:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="authorize",
            errors=errors,
            description_placeholders={"host": self.host}
        )

class FreeboxCallerIDOptionsFlow(config_entries.OptionsFlow):
    """Gère les options via le bouton Configurer de l'UI."""

    def __init__(self, config_entry):
        """Initialisation."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Gère le formulaire des options."""
        if user_input is not None:
            # Sauvegarde les nouvelles options et ferme la fenêtre
            return self.async_create_entry(title="", data=user_input)

        # Récupère l'intervalle actuel (soit depuis les options, soit depuis la config initiale, soit par défaut)
        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, 
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )

        # Affiche le formulaire avec un slider / champ numérique (min 1 sec, max 60 sec)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_SCAN_INTERVAL, 
                    default=current_interval
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60))
            })
        )
