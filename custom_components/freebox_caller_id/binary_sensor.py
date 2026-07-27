"""Capteur binaire pour la sonnerie de la Freebox."""
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    """Configuration du binary_sensor."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FreeboxRingingSensor(coordinator)])

class FreeboxRingingSensor(CoordinatorEntity, BinarySensorEntity):
    """Entité représentant l'état de sonnerie."""
    
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Freebox Sonnerie"
        self._attr_unique_id = f"{DOMAIN}_ringing"
        self._attr_device_class = BinarySensorDeviceClass.SOUND
        self._attr_icon = "mdi:phone-ring"

    @property
    def is_on(self):
        """Retourne True si le téléphone est en train de sonner."""
        if self.coordinator.data:
            return self.coordinator.data.get("is_ringing", False)
        return False
        
    @property
    def extra_state_attributes(self):
        """Ajoute toutes les informations de l'appel entrant dans les attributs."""
        if self.coordinator.data:
            return {
                "caller_name": self.coordinator.data.get("caller_name"),
                "caller_number": self.coordinator.data.get("caller_number"),
                "call_datetime": self.coordinator.data.get("datetime")
            }
        return {}
