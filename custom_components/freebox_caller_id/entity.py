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

        # Récupération de la pièce saisie par l'utilisateur (ex: "Salon")
        area = self._entry.data.get("area", "").strip()
        short_id = self._entry.entry_id[:6]

        # Construction exacte de votre nom : "Salon Freebox Phone a1b2c3" (ou "Freebox Phone a1b2c3" si vide)
        device_name = f"{area} Freebox Phone ({short_id})".strip() if area else f"Freebox Phone ({short_id})"

        firmware_ver = None
        box_model = None

        if self.coordinator.data and isinstance(self.coordinator.data, dict):
            system_data = self.coordinator.data.get("system", {})
            firmware_ver = system_data.get("firmware_version")

            model_info = system_data.get("model_info", {})
            raw_model = None

            if isinstance(model_info, dict):
                raw_model = model_info.get("pretty_name") or model_info.get("name")
            elif isinstance(model_info, str):
                raw_model = model_info

            if not raw_model:
                raw_model = system_data.get("board_name")

            if raw_model:
                box_model = FREEBOX_MODELS.get(raw_model.lower(), raw_model)

        model_str = f"Freebox Server (modèle {box_model})" if box_model else "Freebox Server"

        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=device_name,
            manufacturer="Free",
            model=model_str,
            sw_version=firmware_ver,
            configuration_url=f"http://{host}",
            suggested_area=area if area else None,  # Place automatiquement l'appareil dans la bonne pièce dans HA
        )
