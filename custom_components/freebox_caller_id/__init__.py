"""Intégration Custom Freebox Caller ID pour Home Assistant."""
import logging
from datetime import timedelta
import hmac
import hashlib

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, EVENT_INCOMING_CALL, CONF_HOST, CONF_APP_TOKEN, CONF_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialisation du composant via l'interface UI."""
    host = entry.data[CONF_HOST]
    app_id = "fr.ha.callerid"
    app_token = entry.data[CONF_APP_TOKEN]
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, 2)

    hass.data.setdefault(DOMAIN, {})

    session_token = None
    last_processed_call_id = None

    async def async_get_session(session):
        nonlocal session_token
        try:
            async with session.get(f"http://{host}/api/v4/login/") as resp:
                data = await resp.json()
                challenge = data["result"]["challenge"]

            password = hmac.new(
                app_token.encode(), challenge.encode(), hashlib.sha1
            ).hexdigest()

            payload = {"app_id": app_id, "password": password}
            async with session.post(f"http://{host}/api/v4/login/session/", json=payload) as resp:
                data = await resp.json()
                if data.get("success"):
                    session_token = data["result"]["session_token"]
                    return True
        except Exception as err:
            _LOGGER.error("Erreur de connexion Freebox OS: %s", err)
        return False

    async def poll_freebox_calls(now=None):
        nonlocal session_token, last_processed_call_id
        session = async_get_clientsession(hass)

        if not session_token:
            if not await async_get_session(session):
                return

        try:
            headers = {"X-Fbx-App-Auth": session_token}
            async with session.get(f"http://{host}/api/v4/call/log/", headers=headers) as resp:
                if resp.status == 403:
                    if await async_get_session(session):
                        headers["X-Fbx-App-Auth"] = session_token
                        async with session.get(f"http://{host}/api/v4/call/log/", headers=headers) as resp2:
                            data = await resp2.json()
                    else:
                        return
                else:
                    data = await resp.json()

                if data.get("success") and data.get("result"):
                    last_call = data["result"][0]
                    call_id = last_call.get("id")
                    duration = last_call.get("duration", 0)

                    if last_processed_call_id is None:
                        last_processed_call_id = call_id
                        return

                    if call_id != last_processed_call_id and duration == 0:
                        last_processed_call_id = call_id
                        event_data = {
                            "id": call_id,
                            "number": last_call.get("number"),
                            "name": last_call.get("name") or "Inconnu",
                            "type": last_call.get("type"),
                            "datetime": last_call.get("datetime"),
                        }
                        hass.bus.async_fire(EVENT_INCOMING_CALL, event_data)

        except Exception as err:
            _LOGGER.error("Erreur API Freebox: %s", err)

    # Lancement du polling et sauvegarde de l'outil d'annulation
    remove_listener = async_track_time_interval(hass, poll_freebox_calls, timedelta(seconds=scan_interval))
    hass.data[DOMAIN][entry.entry_id] = remove_listener

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Désinstallation de l'intégration."""
    remove_listener = hass.data[DOMAIN].pop(entry.entry_id)
    remove_listener() # Arrête le polling
    return True
