"""Coordinator for the Freebox Caller ID integration."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from datetime import timedelta
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
    """Manage updates from the Freebox."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: HomeAssistantClientSession,
        host: str,
        app_token: str,
        scan_interval: int,
        ringing_timeout: int,
    ) -> None:
        """Initialize the coordinator."""
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
        self.ringing_timeout = ringing_timeout

        self.session_token: str | None = None
        self.system_info: FreeboxSystemInfo = {}

        # ID of the most recently observed call.
        #
        # The first call returned after startup is only used to initialize
        # this value. It must not generate an event because it may have
        # existed before Home Assistant started.
        self._last_seen_call_id: int | None = None

        self._consecutive_failures = 0

    async def _async_get_session(self) -> bool:
        """Obtain a new session token from the Freebox."""
        try:
            timeout = aiohttp.ClientTimeout(total=5)

            async with self.session.get(
                f"http://{self.host}/api/v4/login/",
                timeout=timeout,
            ) as response:
                if response.status != 200:
                    return False

                data = cast(
                    FreeboxLoginResponse,
                    await response.json(),
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
            ) as response:
                if response.status != 200:
                    return False

                data = cast(
                    FreeboxSessionResponse,
                    await response.json(),
                )

                if not data["success"]:
                    return False

                self.session_token = data["result"]["session_token"]
                return True

        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug(
                "Failed to obtain Freebox session: %s",
                err,
            )

        return False

    async def _async_fetch_system_info(
        self,
        headers: dict[str, str],
    ) -> None:
        """Fetch Freebox system information once."""
        if self.system_info:
            return

        try:
            timeout = aiohttp.ClientTimeout(total=5)

            async with self.session.get(
                f"http://{self.host}/api/v4/system/",
                headers=headers,
                timeout=timeout,
            ) as response:
                if response.status == 200:
                    data = cast(
                        FreeboxSystemResponse,
                        await response.json(),
                    )

                    if data["success"]:
                        self.system_info = data["result"]

                        _LOGGER.debug(
                            "Freebox system information retrieved: %s",
                            self.system_info,
                        )
                else:
                    _LOGGER.warning(
                        "Unable to retrieve /api/v4/system/ "
                        "(HTTP %d)",
                        response.status,
                    )

        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Error retrieving Freebox system information: %s",
                err,
            )

    def _handle_failure(self, reason: str) -> None:
        """Handle a failed update with exponential backoff."""
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
                "Lost connection to Freebox (%s). "
                "Reconnection attempts in progress "
                "(next attempt in %ds).",
                reason,
                backoff_seconds,
            )
        else:
            _LOGGER.debug(
                "Freebox still unavailable "
                "(failure #%d: %s). Next attempt in %ds.",
                self._consecutive_failures,
                reason,
                backoff_seconds,
            )

        raise UpdateFailed(f"Freebox unavailable: {reason}")

    def _handle_success(self) -> None:
        """Restore normal polling after a successful update."""
        if self._consecutive_failures > 0:
            _LOGGER.info(
                "Connection to Freebox restored after %d failure(s). "
                "Returning to normal polling interval (%ds).",
                self._consecutive_failures,
                self.base_scan_interval,
            )

            self._consecutive_failures = 0
            self.update_interval = timedelta(
                seconds=self.base_scan_interval,
            )

    @staticmethod
    def _is_incoming(call_type: CallType) -> bool:
        """Return whether a call is incoming."""
        return call_type in ("accepted", "missed")

    def _is_ringing(
        self,
        *,
        call_type: CallType,
        duration: int,
        call_time: float,
        now: float,
    ) -> bool:
        """Determine whether the current call is ringing."""
        if not self._is_incoming(call_type):
            return False

        # duration == 0 is intentionally retained:
        # this is the observed Freebox behavior while the phone is ringing.
        if duration != 0:
            return False

        age = now - call_time

        return 0 <= age < self.ringing_timeout

    def _fire_incoming_call_event(
        self,
        call: FreeboxCall,
        call_type: CallType,
        call_time: float,
    ) -> None:
        """Fire an event for a newly detected incoming call."""
        call_id = call["id"]

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
        """Fetch the latest data from the Freebox API."""
        timeout = aiohttp.ClientTimeout(total=5)

        try:
            if not self.session_token and not await self._async_get_session():
                self._handle_failure("Unable to open a session")

            assert self.session_token is not None

            headers = {"X-Fbx-App-Auth": self.session_token}

            await self._async_fetch_system_info(headers)

            async with self.session.get(
                f"http://{self.host}/api/v4/call/log/",
                headers=headers,
                timeout=timeout,
            ) as response:
                if response.status == 403:
                    _LOGGER.debug(
                        "Session expired (403), attempting renewal..."
                    )

                    if await self._async_get_session():
                        assert self.session_token is not None
                        headers["X-Fbx-App-Auth"] = self.session_token

                        await self._async_fetch_system_info(headers)

                        async with self.session.get(
                            f"http://{self.host}/api/v4/call/log/",
                            headers=headers,
                            timeout=timeout,
                        ) as retry_response:
                            if retry_response.status != 200:
                                self._handle_failure(
                                    f"HTTP error {retry_response.status}",
                                )

                            data = cast(
                                FreeboxCallLogResponse,
                                await retry_response.json(),
                            )
                    else:
                        self._handle_failure(
                            "Failed to renew the session",
                        )

                elif response.status != 200:
                    self._handle_failure(
                        f"HTTP error {response.status}",
                    )

                else:
                    data = cast(
                        FreeboxCallLogResponse,
                        await response.json(),
                    )

            if not data["success"]:
                self._handle_failure("Invalid API response")

            self._handle_success()

            calls_result = data.get("result", [])

            # An empty call log is valid.
            if not calls_result:
                return {
                    "system": self.system_info,
                }

            # The Freebox call log is ordered from the most recent call
            # to the oldest one.
            last_call = calls_result[0]

            call_id = last_call.get("id")
            call_type = last_call.get("type")
            duration = last_call.get("duration", 0)
            call_time = last_call.get("datetime")

            if not isinstance(call_id, int):
                self._handle_failure(
                    "Invalid Freebox call ID",
                )

            if call_type not in (
                "accepted",
                "missed",
                "outgoing",
            ):
                self._handle_failure(
                    "Invalid Freebox call type",
                )

            if not isinstance(duration, int):
                self._handle_failure(
                    "Invalid Freebox call duration",
                )

            if not isinstance(call_time, (int, float)):
                self._handle_failure(
                    "Invalid Freebox call timestamp",
                )

            typed_call_type: CallType = call_type
            typed_call_time = float(call_time)
            now = time.time()

            # Detect only a new entry at the head of the call log.
            #
            # The first observed call initializes the reference and does
            # not generate an event, because it may predate Home Assistant.
            if self._last_seen_call_id is None:
                self._last_seen_call_id = call_id

            elif call_id != self._last_seen_call_id:
                self._last_seen_call_id = call_id

                if self._is_incoming(typed_call_type):
                    self._fire_incoming_call_event(
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

            recent_calls: list[FreeboxRecentCall] = []

            for call in calls_result[:10]:
                recent_call_id = call.get("id")
                recent_call_type = call.get("type")
                recent_duration = call.get("duration", 0)
                recent_timestamp = call.get("datetime")

                if not isinstance(recent_call_id, int):
                    continue

                if recent_call_type not in (
                    "accepted",
                    "missed",
                    "outgoing",
                ):
                    continue

                if not isinstance(recent_duration, int):
                    continue

                if not isinstance(recent_timestamp, (int, float)):
                    continue

                recent_calls.append(
                    {
                        "id": recent_call_id,
                        "number": call.get("number"),
                        "name": call.get("name") or "Inconnu",
                        "type": recent_call_type,
                        "duration": recent_duration,
                        "timestamp": float(recent_timestamp),
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
                "recent_calls": recent_calls,
                "system": self.system_info,
            }

        except (aiohttp.ClientError, TimeoutError) as err:
            self._handle_failure(
                f"Network error / timeout: {err}",
            )

        except UpdateFailed:
            raise

        except Exception as err:
            _LOGGER.exception(
                "Error while retrieving calls",
            )
            self._handle_failure(
                f"Unexpected error: {err}",
            )
