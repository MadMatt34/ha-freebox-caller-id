"""Binary sensor for the Freebox phone ringing state."""

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


PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FreeboxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ringing binary sensor."""
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
    """Binary sensor indicating whether the phone is ringing."""

    _attr_translation_key = "ringing"
    _attr_device_class = BinarySensorDeviceClass.SOUND

    def __init__(
        self,
        coordinator: FreeboxCallerCoordinator,
        entry: FreeboxConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_ringing"

    @property
    def is_on(self) -> bool:
        """Return whether the phone is currently ringing."""
        data: FreeboxCallerData | None = self.coordinator.data

        if data:
            return data.get("is_ringing", False)

        return False

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return additional attributes while ringing."""
        data: FreeboxCallerData | None = self.coordinator.data

        if data and self.is_on:
            return {
                "caller_name": data.get("caller_name"),
                "caller_number": data.get("caller_number"),
                "call_type": data.get("call_type"),
                "datetime": data.get("datetime"),
            }

        return {}
