"""Classe de base pour les entités Freebox Caller ID."""

from __future__ import annotations

from typing import cast

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FreeboxConfigEntry
from .const import CONF_HOST, DOMAIN
from .coordinator import FreeboxCallerCoordinator
from .types import FreeboxCallerData, FreeboxConfigData, FreeboxSystemInfo


class FreeboxCallerIDEntity(
    CoordinatorEntity[FreeboxCallerCoordinator],
):
    """Classe de base partagée par toutes les entités de l'intégration."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FreeboxCallerCoordinator,
        entry: FreeboxConfigEntry,
    ) -> None:
        """Initialise l'entité de base."""
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Informations centralisées de l'appareil."""
        config_data = cast(FreeboxConfigData, self._entry.data)

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

        firmware_ver: str | None = None
        box_model: str | None = None

        data: FreeboxCallerData | None = self.coordinator.data

        if data:
            system_data: FreeboxSystemInfo = data.get(
                "system",
                {},
            )

            firmware_ver = system_data.get("firmware_version")

            model_info = system_data.get("model_info")

            if isinstance(model_info, dict):
                box_model = (
                    model_info.get("pretty_name")
                    or model_info.get("name")
                )
            elif isinstance(model_info, str):
                box_model = model_info

            if not box_model:
                box_model = system_data.get("board_name")

        model_str = (
            f"Freebox Server (modèle {box_model})"
            if box_model
            else "Freebox Server"
        )

        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=device_name,
            manufacturer="Free",
            model=model_str,
            sw_version=firmware_ver,
            configuration_url=f"http://{host}",
            suggested_area=area or None,
        )
