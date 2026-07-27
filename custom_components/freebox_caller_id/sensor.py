"""Capteur affichant le dernier appelant et l'historique récent."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, CONF_HOST


async def async_setup_entry(hass, entry, async_add_entities):
    """Configuration du sensor."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FreeboxLastCallSensor(coordinator, entry)])


class FreeboxLastCallSensor(CoordinatorEntity, SensorEntity):
    """Entité stockant le dernier appel et l'historique des 10 derniers appels."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_call"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_last_call"
        self._attr_icon = "mdi:phone-log"
        self._entry = entry

        # Regroupement sous le MÊME Appareil dans Home Assistant
        host = entry.data.get(CONF_HOST, "mafreebox.freebox.fr")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Freebox Caller ID",
            manufacturer="Free",
            model="Freebox Server",
            configuration_url=f"http://{host}",
        )

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
