"""Base entity for the Freebox Caller ID integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import FreeboxCallerCoordinator


class FreeboxCallerIDEntity(
    CoordinatorEntity[FreeboxCallerCoordinator],
):
    """Base entity shared by all Freebox Caller ID entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FreeboxCallerCoordinator,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        """Return information about the Freebox device."""
        return self.coordinator.device_info
