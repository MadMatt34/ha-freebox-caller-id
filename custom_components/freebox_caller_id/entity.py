"""Classe de base pour les entités Freebox Caller ID."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FreeboxCallerCoordinator
from .const import CONF_HOST, DOMAIN


class FreeboxCallerIDEntity(CoordinatorEntity[FreeboxCallerCoordinator]):
    """Classe de base partagée par toutes les entités de l'intégration."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FreeboxCallerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialise l'entité de base."""
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Informations centralisées de l'appareil."""
        host = self._entry.data.get(CONF_HOST, "mafreebox.freebox.fr")

        # Nom dynamique issu du Config Entry choisi par l'utilisateur
        device_name = self._entry.title or f"Freebox Phone ({self._entry.entry_id[:6]})"

        firmware_ver = None
        box_model = None

        if self.coordinator.data and isinstance(self.coordinator.data, dict):
            system_data = self.coordinator.data.get("system", {})
            firmware_ver = system_data.get("firmware_version")
            model_info = system_data.get("model_info", {})
            if isinstance(model_info, dict):
                box_model = model_info.get("pretty_name") or model_info.get("name")
            if not box_model:
                box_model = system_data.get("board_name")

        model_str = f"{box_model}" if box_model else "Freebox Caller ID"

        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=device_name,
            manufacturer="Free",
            model=model_str,
            sw_version=firmware_ver,
            configuration_url=f"http://{host}",
        )
