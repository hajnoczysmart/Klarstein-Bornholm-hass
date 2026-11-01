"""Polling coordinator for a Klarstein Bornholm heater."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DEVICE_ID,
    CONF_LOCAL_KEY,
    CONF_MODEL,
    CONF_PROTOCOL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .device import BornholmDevice, BornholmError

_LOGGER = logging.getLogger(__name__)

type BornholmConfigEntry = ConfigEntry[BornholmCoordinator]


class BornholmCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the heater and forwards commands to it."""

    config_entry: BornholmConfigEntry

    def __init__(self, hass: HomeAssistant, entry: BornholmConfigEntry) -> None:
        opts = {**entry.data, **entry.options}
        self.device = BornholmDevice(
            host=opts[CONF_HOST],
            device_id=entry.data[CONF_DEVICE_ID],
            local_key=entry.data[CONF_LOCAL_KEY],
            protocol_version=opts[CONF_PROTOCOL],
            model=entry.data[CONF_MODEL],
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return dict(await self.hass.async_add_executor_job(self.device.update))
        except BornholmError as err:
            raise UpdateFailed(str(err)) from err

    async def async_command(self, func: Callable[..., None], *args: Any) -> None:
        """Run a device setter and push the new state to the entities."""
        try:
            await self.hass.async_add_executor_job(func, *args)
        except BornholmError as err:
            raise HomeAssistantError(f"Klarstein Bornholm: {err}") from err
        self.async_set_updated_data(dict(self.device.dps))

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        await self.hass.async_add_executor_job(self.device.close)
