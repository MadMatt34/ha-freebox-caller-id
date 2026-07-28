"""Support du capteur binaire pour la sonnerie Freebox."""
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, CONF_HOST


async def async_setup_entry(hass, entry, async_add_entities):
    """Configuration du binary sensor."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FreeboxRingingSensor(coordinator, entry)])


class FreeboxRingingSensor(CoordinatorEntity, BinarySensorEntity):
    """Capteur binaire indiquant si le téléphone sonne."""

    _attr_has_entity_name = True
    _attr_translation_key = "ringing"
    _attr_device_class = BinarySensorDeviceClass.SOUND

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        # On force l'ID strict en anglais pour tout le monde
        self.entity_id = "binary_sensor.freebox_caller_id_ringing"
        
        self._attr_unique_id = f"{entry.entry_id}_ringing"
        self._attr_icon = "mdi:phone-ring"
        self._entry = entry

        host = entry.data.get(CONF_HOST, "mafreebox.freebox.fr")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Freebox Caller ID",
            manufacturer="Free",
            model="Freebox Server",
            configuration_url=f"http://{host}",
        )

    @property
    def is_on(self) -> bool:
        """Retourne True si le téléphone est en train de sonner."""
        if self.coordinator.data:
            return self.coordinator.data.get("is_ringing", False)
        return False

    @property
    def extra_state_attributes(self) -> dict:
        """Attributs additionnels lors de la sonnerie."""
        if self.coordinator.data and self.is_on:
            return {
                "caller_name": self.coordinator.data.get("caller_name"),
                "caller_number": self.coordinator.data.get("caller_number"),
                "call_type": self.coordinator.data.get("call_type"),
                "datetime": self.coordinator.data.get("datetime"),
            }
        return {}
