"""Fault indicator."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BornholmConfigEntry, BornholmCoordinator
from .entity import BornholmEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BornholmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.device.profile.fault_dp:
        async_add_entities([BornholmFault(coordinator)])


class BornholmFault(BornholmEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: BornholmCoordinator) -> None:
        super().__init__(coordinator, "fault")

    @property
    def is_on(self) -> bool | None:
        code = self.device.fault_code
        if code is None:
            return False
        return code != 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"fault_code": self.device.fault_code}
