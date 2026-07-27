"""Capteur affichant le dernier appelant et l'historique récent."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    """Configuration du sensor."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FreeboxLastCallSensor(coordinator)])

class FreeboxLastCallSensor(CoordinatorEntity, SensorEntity):
    """Entité stockant le dernier appel et l'historique des 10 derniers appels."""
    
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Dernier appel Freebox"
        self._attr_unique_id = f"{DOMAIN}_last_call"
        self._attr_icon = "mdi:phone-log"

    @property
    def native_value(self):
        """Affiche le nom ou le numéro du tout dernier appelant en état principal."""
        if self.coordinator.data:
            name = self.coordinator.data.get("caller_name")
            num = self.coordinator.data.get("caller_number")
            return name if name and name != "Inconnu" else num
        return "Aucun"

    @property
    def extra_state_attributes(self):
        """Expose le dernier appel et la liste des 10 derniers appels dans les attributs."""
        if self.coordinator.data:
            return {
                "number": self.coordinator.data.get("caller_number"),
                "name": self.coordinator.data.get("caller_name"),
                "type": self.coordinator.data.get("call_type"),
                "duration": self.coordinator.data.get("duration"),
                "timestamp": self.coordinator.data.get("datetime"),
                "calls": self.coordinator.data.get("recent_calls", []) # <--- Liste complète ici
            }
        return {"calls": []}
