"""Support du capteur binaire pour la sonnerie Freebox."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import FreeboxCallerCoordinator
from .entity import FreeboxCallerIDEntity
from .types import FreeboxCallerData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configuration du binary sensor."""
    coordinator: FreeboxCallerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FreeboxRingingSensor(coordinator, entry)])


class FreeboxRingingSensor(FreeboxCallerIDEntity, BinarySensorEntity):
    """Capteur binaire indiquant si le téléphone sonne."""

    _attr_translation_key = "ringing"
    _attr_device_class = BinarySensorDeviceClass.SOUND

    def __init__(
        self,
        coordinator: FreeboxCallerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialise le capteur binaire."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_ringing"

    @property
    def is_on(self) -> bool:
        """Retourne True si le téléphone est en train de sonner."""
        data: FreeboxCallerData | None = self.coordinator.data

        if data:
            return data.get("is_ringing", False)

        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Attributs additionnels lors de la sonnerie."""
        data: FreeboxCallerData | None = self.coordinator.data

        if data and self.is_on:
            return {
                "caller_name": data.get("caller_name"),
                "caller_number": data.get("caller_number"),
                "call_type": data.get("call_type"),
                "datetime": data.get("datetime"),
            }

        return {}
