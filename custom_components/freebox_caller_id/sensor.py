"""Capteur affichant le dernier appelant et l'historique récent."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import FreeboxCallerIDEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configuration du sensor."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FreeboxLastCallSensor(coordinator, entry)])


class FreeboxLastCallSensor(FreeboxCallerIDEntity, SensorEntity):
    """Entité stockant le dernier appel et l'historique des 10 derniers appels."""

    _attr_translation_key = "last_call"

    def __init__(self, coordinator, entry) -> None:
        """Initialise le capteur."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_last_call"

    @property
    def native_value(self) -> str:
        """Affiche le nom ou le numéro du tout dernier appelant en état principal."""
        if self.coordinator.data:
            name = self.coordinator.data.get("caller_name")
            num = self.coordinator.data.get("caller_number")
            return name if name and name != "Inconnu" else (num or "Aucun")
        return "Aucun"

    @property
    def extra_state_attributes(self) -> dict:
        """Expose le dernier appel et la liste des 10 derniers appels dans les attributs."""
        if self.coordinator.data:
            return {
                "number": self.coordinator.data.get("caller_number"),
                "name": self.coordinator.data.get("caller_name"),
                "type": self.coordinator.data.get("call_type"),
                "duration": self.coordinator.data.get("duration"),
                "timestamp": self.coordinator.data.get("datetime"),
                "calls": self.coordinator.data.get("recent_calls", []),
            }
        return {"calls": []}
