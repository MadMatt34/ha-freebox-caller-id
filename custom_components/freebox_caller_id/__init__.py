"""Intégration Custom Freebox Caller ID pour Home Assistant."""
import logging
from datetime import timedelta
import hmac
import hashlib
import time

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, EVENT_INCOMING_CALL, CONF_HOST, CONF_APP_TOKEN, CONF_SCAN_INTERVAL, PLATFORMS

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialisation du composant via l'interface UI."""
    host = entry.data[CONF_HOST]
    app_id = "fr.ha.callerid"
    app_token = entry.data[CONF_APP_TOKEN]
    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL, 
        entry.data.get(CONF_SCAN_INTERVAL, 2)
    )

    session = async_get_clientsession(hass)
    
    # Création du coordinateur
    coordinator = FreeboxCallerCoordinator(
        hass, session, host, app_id, app_token, scan_interval
    )
    
    # Premier rafraîchissement des données avant création des entités
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Demande à Home Assistant de charger les fichiers sensor.py et binary_sensor.py
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Dire à Home Assistant d'écouter les modifications des options
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Recharge l'intégration si les options sont modifiées."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Désinstallation de l'intégration."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

class FreeboxCallerCoordinator(DataUpdateCoordinator):
    """Gestionnaire de mise à jour des données Freebox."""
    
    def __init__(self, hass, session, host, app_id, app_token, scan_interval):
        super().__init__(
            hass, _LOGGER, name="Freebox Caller ID",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.session = session
        self.host = host
        self.app_id = app_id
        self.app_token = app_token
        self.session_token = None
        self._last_notified_call_id = None

    async def _async_get_session(self):
        try:
            async with self.session.get(f"http://{self.host}/api/v4/login/") as resp:
                data = await resp.json()
                challenge = data["result"]["challenge"]

            password = hmac.new(
                self.app_token.encode(), challenge.encode(), hashlib.sha1
            ).hexdigest()

            payload = {"app_id": self.app_id, "password": password}
            async with self.session.post(f"http://{self.host}/api/v4/login/session/", json=payload) as resp:
                data = await resp.json()
                if data.get("success"):
                    self.session_token = data["result"]["session_token"]
                    return True
        except Exception as err:
            _LOGGER.error("Erreur d'authentification Freebox: %s", err)
        return False

    async def _async_update_data(self):
        """Récupère les dernières données de l'API Freebox."""
        if not self.session_token:
            if not await self._async_get_session():
                raise UpdateFailed("Impossible d'obtenir une session Freebox.")

        headers = {"X-Fbx-App-Auth": self.session_token}
        try:
            async with self.session.get(f"http://{self.host}/api/v4/call/log/", headers=headers) as resp:
                if resp.status == 403:
                    if await self._async_get_session():
                        headers["X-Fbx-App-Auth"] = self.session_token
                        async with self.session.get(f"http://{self.host}/api/v4/call/log/", headers=headers) as resp2:
                            data = await resp2.json()
                    else:
                        raise UpdateFailed("Renouvellement de session échoué.")
                else:
                    data = await resp.json()

            if data.get("success") and data.get("result"):
                last_call = data["result"][0]
                call_id = last_call.get("id")
                duration = last_call.get("duration", 0)
                call_time = last_call.get("datetime", time.time())
                
                is_ringing = False
                
                # Détermine si le téléphone sonne (durée=0 et appel datant de moins de 45 secondes)
                if duration == 0 and (time.time() - call_time) < 45:
                    is_ringing = True

                # Déclenche l'événement global (pour rétrocompatibilité) lors d'un NOUVEL appel
                if self._last_notified_call_id is None:
                    self._last_notified_call_id = call_id
                elif call_id != self._last_notified_call_id and is_ringing:
                    self._last_notified_call_id = call_id
                    event_data = {
                        "id": call_id,
                        "number": last_call.get("number"),
                        "name": last_call.get("name") or "Inconnu",
                        "type": last_call.get("type"),
                        "datetime": call_time,
                    }
                    self.hass.bus.async_fire(EVENT_INCOMING_CALL, event_data)

                # Ces données sont envoyées aux capteurs (binary_sensor et sensor)
                return {
                    "is_ringing": is_ringing,
                    "caller_name": last_call.get("name") or "Inconnu",
                    "caller_number": last_call.get("number"),
                    "call_type": last_call.get("type"),
                    "duration": duration,
                    "datetime": call_time,
                    "id": call_id,
                }
            else:
                return {}
        except Exception as err:
            raise UpdateFailed(f"Erreur API Freebox: {err}")
