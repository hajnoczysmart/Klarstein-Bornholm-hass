"""Diagnostics: raw datapoints, with the local key redacted."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_LOCAL_KEY
from .coordinator import BornholmConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BornholmConfigEntry
) -> dict[str, Any]:
    device = entry.runtime_data.device
    return {
        "entry": async_redact_data(dict(entry.data), {CONF_LOCAL_KEY}),
        "options": dict(entry.options),
        "profile": device.profile.name,
        "dps": dict(device.dps),
    }
