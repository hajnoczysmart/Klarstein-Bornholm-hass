"""Display and backlight switches."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BornholmConfigEntry, BornholmCoordinator
from .device import BornholmDevice
from .entity import BornholmEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BornholmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    profile = coordinator.device.profile
    entities = []
    if profile.display_dp:
        entities.append(
            BornholmSwitch(
                coordinator,
                "display",
                lambda d: d.display_on,
                lambda d, on: d.set_display(on),
            )
        )
    if profile.backlight_dp:
        entities.append(
            BornholmSwitch(
                coordinator,
                "backlight",
                lambda d: d.backlight_on,
                lambda d, on: d.set_backlight(on),
            )
        )
    async_add_entities(entities)


class BornholmSwitch(BornholmEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: BornholmCoordinator,
        key: str,
        getter: Callable[[BornholmDevice], bool | None],
        setter: Callable[[BornholmDevice, bool], None],
    ) -> None:
        super().__init__(coordinator, key)
        self._attr_translation_key = key
        self._getter = getter
        self._setter = setter

    @property
    def is_on(self) -> bool | None:
        return self._getter(self.device)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self._setter, self.device, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self._setter, self.device, False)
