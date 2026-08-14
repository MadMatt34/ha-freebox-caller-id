"""Coordinator for the Freebox Caller ID integration."""

from __future__ import annotations

from datetime import timedelta
import hashlib
import hmac
import logging
import time

import aiohttp
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import EVENT_INCOMING_CALL

_LOGGER = logging.getLogger(__name__)

MAX_BACKOFF_INTERVAL = 60


class FreeboxCallerCoordinator(DataUpdateCoordinator):
    """Gestionnaire de mise à jour des données Freebox."""

    def __init__(
        self,
        hass,
        session,
        host,
        app_id,
        app_token,
        scan_interval,
        ringing_timeout,
    ):
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

            async with self.session.get(
                f"http://{self.host}/api/v4/login/",
                timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    return False

                data = await resp.json()
                challenge = data["result"]["challenge"]

            password = hmac.new(
                self.app_token.encode(),
                challenge.encode(),
                hashlib.sha1,
            ).hexdigest()

            payload = {
                "app_id": self.app_id,
                "password": password,
            }

            async with self.session.post(
                f"http://{self.host}/api/v4/login/session/",
                json=payload,
                timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    return False

                data = await resp.json()

                if data.get("success"):
                    self.session_token = data["result"]["session_token"]
                    return True

        except (aiohttp.ClientError, TimeoutError, Exception) as err:  # noqa: BLE001
            _LOGGER.debug(
                "Échec de la demande de session Freebox : %s",
                err,
            )

        return False

    async def _async_fetch_system_info(self, headers: dict) -> None:
        """Récupère les informations système une seule fois."""
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
                        _LOGGER.debug(
                            "Données système Freebox récupérées : %s",
                            self.system_info,
                        )
                else:
                    _LOGGER.warning(
                        "Impossible de récupérer /api/v4/system/ "
                        "(Code HTTP %d)",
                        resp_sys.status,
                    )

        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Erreur lors de la récupération des informations "
                "système Freebox : %s",
                err,
            )

    def _handle_failure(self, reason: str):
        """Calcule le backoff exponentiel et gère le niveau de log."""
        self._consecutive_failures += 1
        self.session_token = None
        self.system_info = {}

        backoff_seconds = min(
            MAX_BACKOFF_INTERVAL,
            self.base_scan_interval * (2**self._consecutive_failures),
        )

        self.update_interval = timedelta(seconds=backoff_seconds)

        if self._consecutive_failures == 1:
            _LOGGER.warning(
                "Connexion à la Freebox perdue (%s). "
                "Tentatives de reconnexion en cours "
                "(prochain essai dans %ds).",
                reason,
                backoff_seconds,
            )
        else:
            _LOGGER.debug(
                "Freebox toujours injoignable "
                "(échec #%d : %s). Prochain essai dans %ds.",
                self._consecutive_failures,
                reason,
                backoff_seconds,
            )

        raise UpdateFailed(f"Freebox indisponible : {reason}")

    def _handle_success(self):
        """Rétablit les paramètres normaux après un succès."""
        if self._consecutive_failures > 0:
            _LOGGER.info(
                "Connexion à la Freebox rétablie avec succès après "
                "%d échec(s). Retour au rythme de balayage normal (%ds).",
                self._consecutive_failures,
                self.base_scan_interval,
            )

            self._consecutive_failures = 0
            self.update_interval = timedelta(
                seconds=self.base_scan_interval
            )

    async def _async_update_data(self):
        """Récupère les dernières données de l'API Freebox."""
        timeout = aiohttp.ClientTimeout(total=5)

        try:
            if not self.session_token and not await self._async_get_session():
                self._handle_failure("Impossible d'ouvrir une session")

            headers = {"X-Fbx-App-Auth": self.session_token}

            # Récupération unique des infos système si non encore chargées.
            await self._async_fetch_system_info(headers)

            # Requête du journal d'appels.
            async with self.session.get(
                f"http://{self.host}/api/v4/call/log/",
                headers=headers,
                timeout=timeout,
            ) as resp:
                if resp.status == 403:
                    _LOGGER.debug(
                        "Session expirée (403), tentative de renouvellement..."
                    )

                    if await self._async_get_session():
                        headers["X-Fbx-App-Auth"] = self.session_token
                        await self._async_fetch_system_info(headers)

                        async with self.session.get(
                            f"http://{self.host}/api/v4/call/log/",
                            headers=headers,
                            timeout=timeout,
                        ) as resp2:
                            if resp2.status != 200:
                                self._handle_failure(
                                    f"Erreur HTTP {resp2.status}"
                                )

                            data = await resp2.json()
                    else:
                        self._handle_failure(
                            "Échec du renouvellement de la session"
                        )

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
            call_type = last_call.get(
                "type"
            )  # "accepted", "missed", ou "outgoing"
            duration = last_call.get("duration", 0)
            call_time = last_call.get("datetime", time.time())

            # Un appel entrant Freebox est identifié par un type
            # "accepted" ou "missed" (pas "outgoing").
            is_incoming = (
                call_type in ("accepted", "missed")
                or call_type != "outgoing"
            )

            # La sonnerie s'active si c'est un appel entrant,
            # non décroché (duration == 0) et récent.
            now = time.time()
            is_ringing = (
                is_incoming
                and duration == 0
                and abs(now - call_time) < self.ringing_timeout
            )

            # Déclenchement de l'événement UNIQUEMENT
            # pour un NOUVEL appel ENTRANT.
            if self._last_notified_call_id is None:
                self._last_notified_call_id = call_id

            elif call_id != self._last_notified_call_id:
                self._last_notified_call_id = call_id

                if is_incoming:
                    event_data = {
                        "id": call_id,
                        "number": last_call.get("number"),
                        "name": last_call.get("name") or "Inconnu",
                        "type": call_type,
                        "datetime": call_time,
                    }

                    self.hass.bus.async_fire(
                        EVENT_INCOMING_CALL,
                        event_data,
                    )

            formatted_calls = [
                {
                    "id": call.get("id"),
                    "number": call.get("number"),
                    "name": call.get("name") or "Inconnu",
                    "type": call.get("type"),
                    "duration": call.get("duration", 0),
                    "timestamp": call.get("datetime"),
                }
                for call in last_10_calls
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
            _LOGGER.exception(
                "Erreur lors de la récupération des appels"
            )
            self._handle_failure(f"Erreur inattendue : {err}")
