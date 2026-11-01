"""Climate entity: power, target temperature and heat level."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BornholmConfigEntry, BornholmCoordinator
from .entity import BornholmEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BornholmConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([BornholmClimate(entry.runtime_data)])


class BornholmClimate(BornholmEntity, ClimateEntity):
    _attr_name = None
    _attr_translation_key = "heater"
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_target_temperature_step = 1

    def __init__(self, coordinator: BornholmCoordinator) -> None:
        super().__init__(coordinator, "climate")
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        if self.device.profile.preset_dp:
            features |= ClimateEntityFeature.PRESET_MODE
            self._attr_preset_modes = self.device.preset_options
        self._attr_supported_features = features

    @property
    def temperature_unit(self) -> str:
        return (
            UnitOfTemperature.FAHRENHEIT
            if self.device.fahrenheit
            else UnitOfTemperature.CELSIUS
        )

    @property
    def min_temp(self) -> float:
        return self.device.temp_range[0]

    @property
    def max_temp(self) -> float:
        return self.device.temp_range[1]

    @property
    def hvac_mode(self) -> HVACMode | None:
        on = self.device.is_on
        if on is None:
            return None
        return HVACMode.HEAT if on else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction | None:
        if self.device.is_on is False:
            return HVACAction.OFF
        heating = self.device.is_heating
        if heating is None:
            return None
        return HVACAction.HEATING if heating else HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        return self.device.current_temperature

    @property
    def target_temperature(self) -> float | None:
        return self.device.target_temperature

    @property
    def preset_mode(self) -> str | None:
        return self.device.preset

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self.coordinator.async_command(
            self.device.set_power, hvac_mode == HVACMode.HEAT
        )

    async def async_turn_on(self) -> None:
        await self.coordinator.async_command(self.device.set_power, True)

    async def async_turn_off(self) -> None:
        await self.coordinator.async_command(self.device.set_power, False)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.coordinator.async_command(
                self.device.set_target_temperature, temp
            )
        if (mode := kwargs.get("hvac_mode")) is not None:
            await self.async_set_hvac_mode(mode)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        await self.coordinator.async_command(self.device.set_preset, preset_mode)
