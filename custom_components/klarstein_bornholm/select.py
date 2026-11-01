"""Shut-off timer."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import TIMER_OPTIONS
from .coordinator import BornholmConfigEntry, BornholmCoordinator
from .entity import BornholmEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BornholmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.device.profile.timer_dp:
        async_add_entities([BornholmTimer(coordinator)])


class BornholmTimer(BornholmEntity, SelectEntity):
    _attr_translation_key = "timer"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = TIMER_OPTIONS

    def __init__(self, coordinator: BornholmCoordinator) -> None:
        super().__init__(coordinator, "timer")

    @property
    def current_option(self) -> str | None:
        value = self.device.timer
        return value if value in TIMER_OPTIONS else None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_command(self.device.set_timer, option)
