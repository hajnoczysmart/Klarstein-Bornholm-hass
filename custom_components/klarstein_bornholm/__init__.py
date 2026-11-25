"""Klarstein Bornholm heater integration (local Tuya protocol)."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import BornholmConfigEntry, BornholmCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.LOCK,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: BornholmConfigEntry) -> bool:
    coordinator = BornholmCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BornholmConfigEntry) -> bool:
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_shutdown()
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: BornholmConfigEntry) -> None:
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is not None and dict(entry.options) == coordinator.applied_options:
        return  # data-only update (e.g. new IP found on the LAN); already applied
    await hass.config_entries.async_reload(entry.entry_id)
