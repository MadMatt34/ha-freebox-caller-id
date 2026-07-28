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

        firmware_ver = None
        if self.coordinator.data and isinstance(self.coordinator.data, dict):
            firmware_ver = self.coordinator.data.get("firmware_version")

        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Freebox Server",
            manufacturer="Free",
            model="Freebox Caller ID",
            sw_version=firmware_ver,
            configuration_url=f"http://{host}",
            suggested_area="Entrée",
        )
