"""Intégration Custom Freebox Caller ID pour Home Assistant."""
import logging
from datetime import timedelta
import hmac
import hashlib

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

DOMAIN = "freebox_caller_id"
EVENT_INCOMING_CALL = "freebox_incoming_call"

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Initialisation du composant via configuration.yaml."""
    conf = config.get(DOMAIN)
    if conf is None:
        return True

    host = conf.get("host", "mafreebox.freebox.fr")
    app_id = conf.get("app_id", "fr.ha.callerid")
    app_token = conf.get("app_token")
    scan_interval = conf.get("scan_interval", 2)

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
                if resp.status == 403: # Session expirée
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

                    # Initialisation lors du premier lancement pour ne pas redéclencher d'ancien appel
                    if last_processed_call_id is None:
                        last_processed_call_id = call_id
                        return

                    # Détection d'un NOUVEL appel en cours de sonnerie (duration == 0)
                    if call_id != last_processed_call_id and duration == 0:
                        last_processed_call_id = call_id

                        event_data = {
                            "id": call_id,
                            "number": last_call.get("number"),
                            "name": last_call.get("name") or "Inconnu",
                            "type": last_call.get("type"),
                            "datetime": last_call.get("datetime"),
                        }

                        _LOGGER.info("Appel entrant Freebox détecté : %s", event_data)

                        # Émission de l'événement natif dans le bus Home Assistant
                        hass.bus.async_fire(EVENT_INCOMING_CALL, event_data)

        except Exception as err:
            _LOGGER.error("Erreur lors de la lecture du journal d'appels Freebox: %s", err)

    # Lancement de la boucle de vérification (toutes les X secondes)
    async_track_time_interval(hass, poll_freebox_calls, timedelta(seconds=scan_interval))

    return True
