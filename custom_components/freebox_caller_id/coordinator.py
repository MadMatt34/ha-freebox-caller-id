"""Coordinator for the Freebox Caller ID integration."""

from __future__ import annotations

from datetime import timedelta
import hashlib
import hmac
import logging
import time
from typing import cast

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import HomeAssistantClientSession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import APP_ID, EVENT_INCOMING_CALL
from .types import (
    CallType,
    FreeboxCall,
    FreeboxCallLogResponse,
    FreeboxCallerData,
    FreeboxChallengeResult,
    FreeboxIncomingCallEvent,
    FreeboxLoginResponse,
    FreeboxRecentCall,
    FreeboxSessionResponse,
    FreeboxSystemInfo,
    FreeboxSystemResponse,
)

_LOGGER = logging.getLogger(__name__)

MAX_BACKOFF_INTERVAL = 60


class FreeboxCallerCoordinator(DataUpdateCoordinator[FreeboxCallerData]):
    """Gestionnaire de mise à jour des données Freebox."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: HomeAssistantClientSession,
        host: str,
        app_token: str,
        scan_interval: int,
        ringing_timeout: int,
    ) -> None:
        """Initialise le coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Freebox Caller ID",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.session = session
        self.host = host
        self.app_id = APP_ID
        self.app_token = app_token
        self.base_scan_interval = scan_interval
        self.session_token: str | None = None
        self.system_info: FreeboxSystemInfo = {}

        # IDs des appels déjà observés.
        #
        # Ils sont initialisés avec le contenu du premier snapshot afin
        # qu'un redémarrage de Home Assistant ne génère pas artificiellement
        # un événement pour un appel déjà présent dans le journal.
        self._seen_call_ids: set[int] = set()
        self._calls_initialized = False

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

                data = cast(
                    FreeboxLoginResponse,
                    await resp.json(),
                )
                result: FreeboxChallengeResult = data["result"]
                challenge = result["challenge"]

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

                data = cast(
                    FreeboxSessionResponse,
                    await resp.json(),
                )

                if not data["success"]:
                    return False

                self.session_token = data["result"]["session_token"]
                return True

        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug(
                "Échec de la demande de session Freebox : %s",
                err,
            )

        return False

    async def _async_fetch_system_info(
        self,
        headers: dict[str, str],
    ) -> None:
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
                    sys_json = cast(
                        FreeboxSystemResponse,
                        await resp_sys.json(),
                    )

                    if sys_json["success"]:
                        self.system_info = sys_json["result"]

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

    def _handle_failure(self, reason: str) -> None:
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

    def _handle_success(self) -> None:
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
                seconds=self.base_scan_interval,
            )

    def _update_seen_call_ids(
        self,
        calls: list[FreeboxCall],
    ) -> set[int]:
        """Met à jour les appels connus et retourne les nouveaux IDs."""
        current_call_ids = {
            call_id
            for call in calls
            if isinstance(call_id := call.get("id"), int)
        }

        if not self._calls_initialized:
            self._seen_call_ids = current_call_ids
            self._calls_initialized = True
            return set()

        new_call_ids = current_call_ids - self._seen_call_ids
        self._seen_call_ids = current_call_ids

        return new_call_ids

    def _is_ringing(
        self,
        *,
        call_type: CallType,
        duration: int,
        call_time: float,
        now: float,
    ) -> bool:
        """Détermine si un appel entrant est actuellement en sonnerie."""
        if call_type not in ("accepted", "missed"):
            return False

        # duration == 0 est volontairement conservé :
        # c'est le comportement observé sur les Freebox pendant la sonnerie.
        if duration != 0:
            return False

        age = now - call_time

        return 0 <= age < self.ringing_timeout

    def _fire_incoming_call_event(
        self,
        call_id: int,
        call: FreeboxCall,
        call_type: CallType,
        call_time: float,
    ) -> None:
        """Émet l'événement pour un nouvel appel entrant."""
        event_data: FreeboxIncomingCallEvent = {
            "id": call_id,
            "number": call.get("number"),
            "name": call.get("name") or "Inconnu",
            "type": call_type,
            "datetime": call_time,
        }

        self.hass.bus.async_fire(
            EVENT_INCOMING_CALL,
            event_data,
        )

    async def _async_update_data(self) -> FreeboxCallerData:
        """Récupère les dernières données de l'API Freebox."""
        timeout = aiohttp.ClientTimeout(total=5)

        try:
            if not self.session_token and not await self._async_get_session():
                self._handle_failure("Impossible d'ouvrir une session")

            assert self.session_token is not None

            headers = {"X-Fbx-App-Auth": self.session_token}

            await self._async_fetch_system_info(headers)

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
                        assert self.session_token is not None
                        headers["X-Fbx-App-Auth"] = self.session_token

                        await self._async_fetch_system_info(headers)

                        async with self.session.get(
                            f"http://{self.host}/api/v4/call/log/",
                            headers=headers,
                            timeout=timeout,
                        ) as resp2:
                            if resp2.status != 200:
                                self._handle_failure(
                                    f"Erreur HTTP {resp2.status}",
                                )

                            data = cast(
                                FreeboxCallLogResponse,
                                await resp2.json(),
                            )
                    else:
                        self._handle_failure(
                            "Échec du renouvellement de la session",
                        )

                elif resp.status != 200:
                    self._handle_failure(f"Erreur HTTP {resp.status}")

                else:
                    data = cast(
                        FreeboxCallLogResponse,
                        await resp.json(),
                    )

            if not data["success"]:
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
            call_type = last_call.get("type")
            duration = last_call.get("duration", 0)
            call_time = last_call.get("datetime", time.time())

            if not isinstance(call_id, int):
                self._handle_failure(
                    "Identifiant d'appel Freebox invalide",
                )

            if call_type not in ("accepted", "missed", "outgoing"):
                self._handle_failure(
                    "Type d'appel Freebox invalide",
                )

            if not isinstance(duration, int):
                self._handle_failure(
                    "Durée d'appel Freebox invalide",
                )

            if not isinstance(call_time, (int, float)):
                self._handle_failure(
                    "Horodatage d'appel Freebox invalide",
                )

            typed_call_type: CallType = call_type
            typed_call_time = float(call_time)
            now = time.time()

            new_call_ids = self._update_seen_call_ids(last_10_calls)

            if call_id in new_call_ids and typed_call_type in (
                "accepted",
                "missed",
            ):
                self._fire_incoming_call_event(
                    call_id,
                    last_call,
                    typed_call_type,
                    typed_call_time,
                )

            is_ringing = self._is_ringing(
                call_type=typed_call_type,
                duration=duration,
                call_time=typed_call_time,
                now=now,
            )

            formatted_calls: list[FreeboxRecentCall] = []

            for call in last_10_calls:
                formatted_call_id = call.get("id")
                formatted_call_type = call.get("type")
                formatted_duration = call.get("duration", 0)
                formatted_timestamp = call.get("datetime")

                if not isinstance(formatted_call_id, int):
                    continue

                if formatted_call_type not in (
                    "accepted",
                    "missed",
                    "outgoing",
                ):
                    continue

                if not isinstance(formatted_duration, int):
                    continue

                if not isinstance(formatted_timestamp, (int, float)):
                    continue

                formatted_calls.append(
                    {
                        "id": formatted_call_id,
                        "number": call.get("number"),
                        "name": call.get("name") or "Inconnu",
                        "type": formatted_call_type,
                        "duration": formatted_duration,
                        "timestamp": float(formatted_timestamp),
                    }
                )

            return {
                "is_ringing": is_ringing,
                "caller_name": last_call.get("name") or "Inconnu",
                "caller_number": last_call.get("number"),
                "call_type": typed_call_type,
                "duration": duration,
                "datetime": typed_call_time,
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
                "Erreur lors de la récupération des appels",
            )
            self._handle_failure(f"Erreur inattendue : {err}")
