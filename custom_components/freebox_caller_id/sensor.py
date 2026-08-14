"""Capteur affichant le dernier appelant et l'historique récent."""

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
    """Configuration du sensor."""
    async_add_entities(
        [
            FreeboxLastCallSensor(
                entry.runtime_data,
                entry,
            )
        ]
    )


class FreeboxLastCallSensor(FreeboxCallerIDEntity, SensorEntity):
    """Entité stockant le dernier appel et l'historique des 10 derniers appels."""

    _attr_translation_key = "last_call"

    def __init__(
        self,
        coordinator: FreeboxCallerCoordinator,
        entry: FreeboxConfigEntry,
    ) -> None:
        """Initialise le capteur."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_last_call"

    @property
    def native_value(self) -> str:
        """Affiche le nom ou le numéro du tout dernier appelant."""
        data: FreeboxCallerData | None = self.coordinator.data

        if data:
            name = data.get("caller_name")
            number = data.get("caller_number")

            return (
                name
                if name and name != "Inconnu"
                else (number or "Aucun")
            )

        return "Aucun"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose le dernier appel et l'historique."""
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
