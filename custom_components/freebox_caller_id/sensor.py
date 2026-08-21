"""Sensor displaying the latest caller and recent call history."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
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
    """Set up the last call sensor."""
    async_add_entities(
        [
            FreeboxLastCallSensor(
                entry.runtime_data,
                entry,
            )
        ]
    )


class FreeboxLastCallSensor(FreeboxCallerIDEntity, SensorEntity):
    """Store the latest call and the recent call history."""

    _attr_translation_key = "last_call"

    def __init__(
        self,
        coordinator: FreeboxCallerCoordinator,
        entry: FreeboxConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_last_call"

    @property
    def native_value(self) -> str:
        """Return the name or number of the latest caller."""
        data: FreeboxCallerData | None = self.coordinator.data

        if data:
            name = data.get("caller_name")
            number = data.get("caller_number")

            return name if name and name != "Inconnu" else (number or "Aucun")

        return "Aucun"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose the latest call and recent history."""
        data: FreeboxCallerData | None = self.coordinator.data

        if data:
            return {
                "number": data.get("caller_number"),
                "name": data.get("caller_name"),
                "type": data.get("call_type"),
                "duration": data.get("duration"),
                "timestamp": data.get("datetime"),
                "calls": data.get("recent_calls", []),
            }

        return {"calls": []}
