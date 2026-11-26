"""Polling coordinator for a Klarstein Bornholm heater."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DEVICE_ID,
    CONF_DP_SPEC,
    CONF_LOCAL_KEY,
    CONF_MODEL,
    CONF_PROTOCOL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .device import BornholmDevice, BornholmError, find_on_lan, sweep_subnet

_LOGGER = logging.getLogger(__name__)

# How often (at most) to search the LAN for a heater that stopped answering
REDISCOVER_INTERVAL = 300  # seconds

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
            dp_spec=entry.data.get(CONF_DP_SPEC),
        )
        # options this instance runs with; an options change from the IP
        # rediscovery below must not trigger a reload
        self.applied_options = dict(entry.options)
        self._last_rediscovery = -REDISCOVER_INTERVAL
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
            if not await self._async_rediscover():
                raise UpdateFailed(str(err)) from err
        # the heater was found at a new address: try once more right away
        try:
            return dict(await self.hass.async_add_executor_job(self.device.update))
        except BornholmError as err:
            raise UpdateFailed(str(err)) from err

    async def _async_rediscover(self) -> bool:
        """Find the heater on the LAN if its IP or protocol changed.

        Typical cause: the router handed out new DHCP addresses and another
        heater now answers on the old IP (Tuya error 914) or nothing does (905).
        """
        now = time.monotonic()
        if now - self._last_rediscovery < REDISCOVER_INTERVAL:
            return False
        self._last_rediscovery = now

        entry = self.config_entry
        current = {**entry.data, **entry.options}
        found = await self.hass.async_add_executor_job(
            find_on_lan, entry.data[CONF_DEVICE_ID]
        )
        if not found.get("ip"):
            # broadcasts don't cross routers: ask each host on the heater's subnet
            found = await self.hass.async_add_executor_job(
                sweep_subnet,
                current[CONF_HOST],
                entry.data[CONF_DEVICE_ID],
                entry.data[CONF_LOCAL_KEY],
                current[CONF_PROTOCOL],
            )
        if not found.get("ip"):
            _LOGGER.warning(
                "Klarstein Bornholm %s: not found on the network (last IP %s)",
                entry.title, current[CONF_HOST],
            )
            return False

        host = found["ip"]
        version = found.get("version") or current[CONF_PROTOCOL]
        if host == current[CONF_HOST] and version == current[CONF_PROTOCOL]:
            return False

        _LOGGER.warning(
            "Klarstein Bornholm %s moved from %s (v%s) to %s (v%s); updating",
            entry.title, current[CONF_HOST], current[CONF_PROTOCOL], host, version,
        )
        await self.hass.async_add_executor_job(self.device.set_address, host, version)

        new_data = {**entry.data, CONF_HOST: host, CONF_PROTOCOL: version}
        new_options = dict(entry.options)
        if CONF_HOST in new_options:
            new_options[CONF_HOST] = host
        if CONF_PROTOCOL in new_options:
            new_options[CONF_PROTOCOL] = version
        self.applied_options = new_options
        self.hass.config_entries.async_update_entry(
            entry, data=new_data, options=new_options
        )
        return True

    async def async_command(self, func: Callable[..., None], *args: Any) -> None:
        """Run a device setter and push the new state to the entities."""
        try:
            await self.hass.async_add_executor_job(func, *args)
        except BornholmError as err:
            self.hass.async_create_task(self.async_request_refresh())
            raise HomeAssistantError(f"Klarstein Bornholm: {err}") from err
        self.async_set_updated_data(dict(self.device.dps))

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        await self.hass.async_add_executor_job(self.device.close)
