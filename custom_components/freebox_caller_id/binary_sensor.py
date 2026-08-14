"""Support du capteur binaire pour la sonnerie Freebox."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FreeboxConfigEntry
from .coordinator import FreeboxCallerCoordinator
from .entity import FreeboxCallerIDEntity
from .types import FreeboxCallerData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FreeboxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configuration du binary sensor."""
    async_add_entities(
        [
            FreeboxRingingSensor(
                entry.runtime_data,
                entry,
            )
        ]
    )


class FreeboxRingingSensor(
    FreeboxCallerIDEntity,
    BinarySensorEntity,
):
    """Capteur binaire indiquant si le téléphone sonne."""

    _attr_translation_key = "ringing"
    _attr_device_class = BinarySensorDeviceClass.SOUND

    def __init__(
        self,
        coordinator: FreeboxCallerCoordinator,
        entry: FreeboxConfigEntry,
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
    def extra_state_attributes(self) -> dict[str, object]:
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
