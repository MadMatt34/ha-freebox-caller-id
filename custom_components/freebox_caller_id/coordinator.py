"""Coordinator for the Freebox Caller ID integration."""

from __future__ import annotations

from datetime import timedelta
import hashlib
import hmac
import logging
import time
from typing import NoReturn, cast

import aiohttp
from aiohttp import ClientSession
from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import APP_ID, DOMAIN, EVENT_INCOMING_CALL
from .types import (
    CallType,
    FreeboxCall,
    FreeboxCallerData,
    FreeboxCallLogResponse,
    FreeboxChallengeResult,
    FreeboxErrorResponse,
    FreeboxIncomingCallEvent,
    FreeboxLoginResponse,
    FreeboxRecentCall,
    FreeboxSessionResponse,
    FreeboxSystemInfo,
    FreeboxSystemResponse,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 5


class FreeboxCallerCoordinator(DataUpdateCoordinator[FreeboxCallerData]):
    """Manage updates from the Freebox."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: ClientSession,
        host: str,
        app_token: str,
        entry_id: str,
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
        self.entry_id = entry_id
        self.ringing_timeout = ringing_timeout

        self.session_token: str | None = None
        self.system_info: FreeboxSystemInfo = {}
        self._device_info = self._create_default_device_info()
        self._device_info_signature: tuple[str, str | None] = (
            "Freebox Server",
            None,
        )

        # ID of the most recently observed call.
        #
        # The first call returned after startup is only used to initialize
        # this value. It must not generate an event because it may have
        # existed before Home Assistant started.
        self._last_seen_call_id: int | None = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return the cached device information."""
        return self._device_info

    def _create_default_device_info(self) -> DeviceInfo:
        """Create the default device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry_id)},
            name="Freebox Phone",
            manufacturer="Free",
            model="Freebox Server",
            configuration_url=f"http://{self.host}",
        )

    def _update_device_info(self) -> None:
        """Update cached device information."""
        firmware_version = self.system_info.get("firmware_version")

        box_model: str | None = None
        model_info = self.system_info.get("model_info")

        if model_info:
            if isinstance(model_info, str):
                box_model = model_info
            else:
                box_model = model_info.get("pretty_name") or model_info.get("name")

        if not box_model:
            box_model = self.system_info.get("board_name")

        model = f"Freebox Server (modèle {box_model})" if box_model else "Freebox Server"

        signature = (
            model,
            firmware_version,
        )

        if signature == self._device_info_signature:
            return

        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, self.entry_id)},
            name="Freebox Phone",
            manufacturer="Free",
            model=model,
            sw_version=firmware_version,
            configuration_url=f"http://{self.host}",
        )
        self._device_info_signature = signature

        # On the first refresh the device has not yet been created by the
        # entity platform. After that, update only the existing device so
        # user-controlled fields such as area and name are left untouched.
        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, self.entry_id)},
        )

        if device is not None:
            device_registry.async_update_device(
                device.id,
                manufacturer="Free",
                model=model,
                sw_version=firmware_version,
                configuration_url=f"http://{self.host}",
            )

    async def _async_get_session(self) -> bool:
        """Obtain a new session token from the Freebox."""
        try:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

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
                if response.status == 403:
                    try:
                        raw_data = await response.json()
                    except ValueError:
                        return False

                    if isinstance(raw_data, dict):
                        error_data = cast(
                            FreeboxErrorResponse,
                            raw_data,
                        )

                        if error_data.get("error_code") == "invalid_token":
                            raise ConfigEntryAuthFailed(
                                "Freebox application token is invalid or revoked",
                            )

                    return False

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

        except (
            aiohttp.ClientError,
            TimeoutError,
            ValueError,
            KeyError,
            TypeError,
        ) as err:
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
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

            async with self.session.get(
                f"http://{self.host}/api/v4/system/",
                headers=headers,
                timeout=timeout,
            ) as response:
                if response.status != 200:
                    _LOGGER.warning(
                        "Unable to retrieve /api/v4/system/ (HTTP %d)",
                        response.status,
                    )
                    return

                data = cast(
                    FreeboxSystemResponse,
                    await response.json(),
                )

                if not data["success"]:
                    _LOGGER.warning(
                        "Freebox /api/v4/system/ returned an unsuccessful response.",
                    )
                    return

                self.system_info = data["result"]
                self._update_device_info()

                _LOGGER.debug(
                    "Freebox system information retrieved: %s",
                    self.system_info,
                )

        except (
            aiohttp.ClientError,
            TimeoutError,
            ValueError,
            KeyError,
            TypeError,
        ) as err:
            _LOGGER.warning(
                "Error retrieving Freebox system information: %s",
                err,
            )

    def _handle_failure(self, reason: str) -> NoReturn:
        """Handle a failed update."""
        self.session_token = None

        # Force system information to be refreshed after the Freebox
        # comes back online.
        #
        # The cached DeviceInfo itself is intentionally preserved.
        self.system_info = {}

        raise UpdateFailed(
            f"Freebox unavailable: {reason}",
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
        """Fetch the latest data from the Freebox."""
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

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
                        "Session expired (403), attempting renewal...",
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

            # The first observed call only initializes the reference.
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

        except ConfigEntryAuthFailed:
            raise

        except (
            aiohttp.ClientError,
            TimeoutError,
            ValueError,
            KeyError,
            TypeError,
        ) as err:
            self._handle_failure(
                f"Freebox communication error: {err}",
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
