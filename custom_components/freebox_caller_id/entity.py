"""Base entity for the Freebox Caller ID integration."""

from __future__ import annotations

from typing import cast

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FreeboxConfigEntry
from .const import CONF_HOST, DOMAIN
from .coordinator import FreeboxCallerCoordinator
from .types import FreeboxConfigData, FreeboxSystemInfo


class FreeboxCallerIDEntity(
    CoordinatorEntity[FreeboxCallerCoordinator],
):
    """Base entity shared by all Freebox Caller ID entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FreeboxCallerCoordinator,
        entry: FreeboxConfigEntry,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)

        self._entry = entry

        self._device_info: DeviceInfo | None = None
        self._device_info_signature: tuple[
            str | None,
            str | None,
        ] | None = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return information about the Freebox device."""
        config_data = cast(
            FreeboxConfigData,
            self._entry.data,
        )

        host = config_data.get(
            CONF_HOST,
            "mafreebox.freebox.fr",
        )

        area = config_data.get("area", "").strip()

        short_id = self._entry.entry_id[:6]

        device_name = (
            f"{area} Freebox Phone ({short_id})"
            if area
            else f"Freebox Phone ({short_id})"
        )

        system_data: FreeboxSystemInfo = {}

        if self.coordinator.data:
            system_data = self.coordinator.data.get(
                "system",
                {},
            )

        # Keep the last known DeviceInfo while the Freebox is offline.
        #
        # The coordinator intentionally clears system_info when the
        # connection is lost. It will be populated again when the Freebox
        # comes back online.
        if system_data:
            firmware_ver = system_data.get("firmware_version")

            box_model: str | None = None
            model_info = system_data.get("model_info")

            if model_info:
                if isinstance(model_info, str):
                    box_model = model_info
                else:
                    box_model = (
                        model_info.get("pretty_name")
                        or model_info.get("name")
                    )

            if not box_model:
                box_model = system_data.get("board_name")

            model_str = (
                f"Freebox Server (modèle {box_model})"
                if box_model
                else "Freebox Server"
            )

            signature = (
                model_str,
                firmware_ver,
            )

            if (
                self._device_info is None
                or self._device_info_signature != signature
            ):
                self._device_info = DeviceInfo(
                    identifiers={(DOMAIN, self._entry.entry_id)},
                    name=device_name,
                    manufacturer="Free",
                    model=model_str,
                    sw_version=firmware_ver,
                    configuration_url=f"http://{host}",
                    suggested_area=area or None,
                )
                self._device_info_signature = signature

        # This should only be possible before the first successful
        # coordinator refresh. Keep the existing fallback behavior.
        if self._device_info is None:
            self._device_info = DeviceInfo(
                identifiers={(DOMAIN, self._entry.entry_id)},
                name=device_name,
                manufacturer="Free",
                model="Freebox Server",
                configuration_url=f"http://{host}",
                suggested_area=area or None,
            )
            self._device_info_signature = (
                "Freebox Server",
                None,
            )

        return self._device_info
