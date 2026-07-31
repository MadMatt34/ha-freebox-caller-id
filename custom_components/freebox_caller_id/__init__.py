"""Intégration Custom Freebox Caller ID pour Home Assistant."""
from __future__ import annotations

from datetime import timedelta
import hashlib
import hmac
import logging
import time

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_APP_TOKEN,
    CONF_HOST,
    CONF_SCAN_INTERVAL,
    DOMAIN,
    EVENT_INCOMING_CALL,
    PLATFORMS,
)

_LOGGER = logging.getLogger(__name__)

MAX_BACKOFF_INTERVAL = 60  # Intervalle maximal en secondes en cas de panne


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialisation du composant via l'interface UI."""
    host = entry.data[CONF_HOST]
    app_id = "fr.ha.callerid"
    app_token = entry.data[CONF_APP_TOKEN]

    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )
    ringing_timeout = entry.options.get(
        CONF_RINGING_TIMEOUT,
        entry.data.get(CONF_RINGING_TIMEOUT, DEFAULT_RINGING_TIMEOUT)
    )

    session = async_get_clientsession(hass)

    coordinator = FreeboxCallerCoordinator(
        hass, session, host, app_id, app_token, scan_interval, ringing_timeout
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

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
    """Gestionnaire de mise à jour des données Freebox avec gestion d'erreurs avancée."""

    def __init__(self, hass, session, host, app_id, app_token, scan_interval, ringing_timeout):
        super().__init__(
            hass,
            _LOGGER,
            name="Freebox Caller ID",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.session = session
        self.host = host
        self.app_id = app_id
        self.app_token = app_token
        self.base_scan_interval = scan_interval
        self.session_token = None
        self.system_info = {}
        self._last_notified_call_id = None
        self._consecutive_failures = 0
        self.ringing_timeout = ringing_timeout

    async def _async_get_session(self) -> bool:
        """Obtient un nouveau token de session auprès de la Freebox."""
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with self.session.get(f"http://{self.host}/api/v4/login/", timeout=timeout) as resp:
                if resp.status != 200:
                    return False
                data = await resp.json()
                challenge = data["result"]["challenge"]

            password = hmac.new(
                self.app_token.encode(), challenge.encode(), hashlib.sha1
            ).hexdigest()

            payload = {"app_id": self.app_id, "password": password}
            async with self.session.post(
                f"http://{self.host}/api/v4/login/session/", json=payload, timeout=timeout
            ) as resp:
                if resp.status != 200:
                    return False
                data = await resp.json()
                if data.get("success"):
                    self.session_token = data["result"]["session_token"]
                    return True
        except (aiohttp.ClientError, TimeoutError, Exception) as err:  # noqa: BLE001
            _LOGGER.debug("Échec de la demande de session Freebox : %s", err)
        return False

    async def _async_fetch_system_info(self, headers: dict) -> None:
        """Récupère les informations système une seule fois au démarrage ou après reconnexion."""
        if self.system_info:
            return
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with self.session.get(
                f"http://{self.host}/api/v4/system/",
                headers=headers,
                timeout=timeout,
            ) as resp_sys:
                if resp_sys.status == 200:
                    sys_json = await resp_sys.json()
                    if sys_json.get("success"):
                        self.system_info = sys_json.get("result", {})
                        _LOGGER.debug("Données système Freebox récupérées : %s", self.system_info)
                else:
                    _LOGGER.warning("Impossible de récupérer /api/v4/system/ (Code HTTP %d)", resp_sys.status)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Erreur lors de la récupération des informations système Freebox : %s", err)

    def _handle_failure(self, reason: str):
        """Calcule le backoff exponentiel et gère le niveau de log."""
        self._consecutive_failures += 1
        self.session_token = None
        self.system_info = {}  # Réinitialise les infos système pour forcer un rechargement à la reconnexion

        backoff_seconds = min(
            MAX_BACKOFF_INTERVAL,
            self.base_scan_interval * (2 ** self._consecutive_failures)
        )
        self.update_interval = timedelta(seconds=backoff_seconds)

        if self._consecutive_failures == 1:
            _LOGGER.warning(
                "Connexion à la Freebox perdue (%s). Tentatives de reconnexion en cours (prochain essai dans %ds).",
                reason, backoff_seconds
            )
        else:
            _LOGGER.debug(
                "Freebox toujours injoignable (échec #%d : %s). Prochain essai dans %ds.",
                self._consecutive_failures, reason, backoff_seconds
            )

        raise UpdateFailed(f"Freebox indisponible : {reason}")

    def _handle_success(self):
        """Rétablit les paramètres normaux après un succès."""
        if self._consecutive_failures > 0:
            _LOGGER.info(
                "Connexion à la Freebox rétablie avec succès après %d échec(s). Retour au rythme de balayage normal (%ds).",
                self._consecutive_failures, self.base_scan_interval
            )
            self._consecutive_failures = 0
            self.update_interval = timedelta(seconds=self.base_scan_interval)

    async def _async_update_data(self):
        """Récupère les dernières données de l'API Freebox."""
        timeout = aiohttp.ClientTimeout(total=5)

        try:
            if not self.session_token and not await self._async_get_session():
                self._handle_failure("Impossible d'ouvrir une session")

            headers = {"X-Fbx-App-Auth": self.session_token}

            # Récupération unique des infos système si non encore chargées
            await self._async_fetch_system_info(headers)

            # Requête du journal d'appels
            async with self.session.get(
                f"http://{self.host}/api/v4/call/log/",
                headers=headers,
                timeout=timeout
            ) as resp:
                if resp.status == 403:
                    _LOGGER.debug("Session expirée (403), tentative de renouvellement...")
                    if await self._async_get_session():
                        headers["X-Fbx-App-Auth"] = self.session_token
                        await self._async_fetch_system_info(headers)
                        async with self.session.get(
                            f"http://{self.host}/api/v4/call/log/",
                            headers=headers,
                            timeout=timeout
                        ) as resp2:
                            if resp2.status != 200:
                                self._handle_failure(f"Erreur HTTP {resp2.status}")
                            data = await resp2.json()
                    else:
                        self._handle_failure("Échec du renouvellement de la session")
                elif resp.status != 200:
                    self._handle_failure(f"Erreur HTTP {resp.status}")
                else:
                    data = await resp.json()

            if not data.get("success"):
                self._handle_failure("Réponse API invalide")

            self._handle_success()

            calls_result = data.get("result", [])
            if not calls_result:
                return {
                    "system": self.system_info,
                }

            last_10_calls = calls_result[:10]
            last_call = last_10_calls[0]

            call_id = last_call.get("id")
            call_type = last_call.get("type")  # "accepted", "missed", ou "outgoing"
            duration = last_call.get("duration", 0)
            call_time = last_call.get("datetime", time.time())

            # Un appel entrant Freebox est identifié par un type "accepted" ou "missed" (pas "outgoing")
            is_incoming = call_type in ("accepted", "missed") or call_type != "outgoing"

            # 1. La sonnerie s'active si c'est un appel entrant, non décroché (duration == 0) et récent (< 60s)
            now = time.time()
            is_ringing = (
                is_incoming
                and duration == 0
                and abs(now - call_time) < self.ringing_timeout
            )

            # 2. Déclenchement de l'événement UNIQUEMENT pour un NOUVEL appel ENTRANT
            if self._last_notified_call_id is None:
                self._last_notified_call_id = call_id
            elif call_id != self._last_notified_call_id:
                self._last_notified_call_id = call_id

                # Déclenchement de l'événement si c'est un nouvel appel entrant
                if is_incoming:
                    event_data = {
                        "id": call_id,
                        "number": last_call.get("number"),
                        "name": last_call.get("name") or "Inconnu",
                        "type": call_type,
                        "datetime": call_time,
                    }
                    self.hass.bus.async_fire(EVENT_INCOMING_CALL, event_data)

            formatted_calls = [
                {
                    "id": c.get("id"),
                    "number": c.get("number"),
                    "name": c.get("name") or "Inconnu",
                    "type": c.get("type"),
                    "duration": c.get("duration", 0),
                    "timestamp": c.get("datetime"),
                }
                for c in last_10_calls
            ]

            return {
                "is_ringing": is_ringing,
                "caller_name": last_call.get("name") or "Inconnu",
                "caller_number": last_call.get("number"),
                "call_type": call_type,
                "duration": duration,
                "datetime": call_time,
                "id": call_id,
                "recent_calls": formatted_calls,
                "system": self.system_info,
            }

        except (aiohttp.ClientError, TimeoutError) as err:
            self._handle_failure(f"Erreur réseau / timeout : {err}")
        except UpdateFailed:
            raise
        except Exception as err:
            _LOGGER.exception("Erreur lors de la récupération des appels")
            self._handle_failure(f"Erreur inattendue : {err}")
