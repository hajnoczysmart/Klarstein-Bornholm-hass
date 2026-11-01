"""Child lock."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
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
    if coordinator.device.profile.child_lock_dp:
        async_add_entities([BornholmChildLock(coordinator)])


class BornholmChildLock(BornholmEntity, LockEntity):
    _attr_translation_key = "child_lock"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: BornholmCoordinator) -> None:
        super().__init__(coordinator, "child_lock")

    @property
    def is_locked(self) -> bool | None:
        return self.device.child_lock

    async def async_lock(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.device.set_child_lock, True)

    async def async_unlock(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.device.set_child_lock, False)
