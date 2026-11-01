"""Timer remaining sensor."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory, UnitOfTime
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
    if coordinator.device.profile.timer_remaining_dp:
        async_add_entities([BornholmTimeRemaining(coordinator)])


class BornholmTimeRemaining(BornholmEntity, SensorEntity):
    _attr_translation_key = "time_remaining"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: BornholmCoordinator) -> None:
        super().__init__(coordinator, "time_remaining")

    @property
    def native_value(self) -> int | None:
        return self.device.timer_remaining
