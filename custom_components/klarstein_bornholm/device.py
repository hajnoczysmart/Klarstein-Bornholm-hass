"""Local Tuya communication with a Klarstein Bornholm heater.

This module has no Home Assistant imports so it can be tested on its own.
All methods are blocking; Home Assistant calls them in an executor.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import tinytuya

from .const import PROFILES, TIMER_OPTIONS, ModelProfile

_LOGGER = logging.getLogger(__name__)


class BornholmError(Exception):
    """Raised when the heater cannot be reached or rejects a command."""


class BornholmDevice:
    """Thin wrapper around tinytuya with Bornholm-specific value mapping."""

    def __init__(
        self,
        host: str,
        device_id: str,
        local_key: str,
        protocol_version: str,
        model: str,
    ) -> None:
        self.profile: ModelProfile = PROFILES[model]
        self._lock = threading.Lock()
        self._dev = tinytuya.Device(
            device_id,
            address=host,
            local_key=local_key,
            version=float(protocol_version),
            connection_timeout=5,
            connection_retry_limit=2,
            connection_retry_delay=1,
        )
        self.dps: dict[str, Any] = {}

    # ------------------------------------------------------------------ I/O

    def _check(self, result: Any) -> dict:
        if not isinstance(result, dict):
            raise BornholmError("No response from heater")
        if "Error" in result or "Err" in result:
            raise BornholmError(
                f"Tuya error {result.get('Err')}: {result.get('Error')}"
            )
        return result

    def update(self) -> dict[str, Any]:
        """Read all DPs from the heater."""
        with self._lock:
            result = self._check(self._dev.status())
        dps = result.get("dps")
        if not isinstance(dps, dict):
            raise BornholmError(f"Unexpected status payload: {result}")
        self.dps.update({str(k): v for k, v in dps.items()})
        return self.dps

    def set_dps(self, values: dict[str, Any]) -> None:
        """Write one or more DPs and merge the echoed state."""
        with self._lock:
            result = self._dev.set_multiple_values(values)
        # Some firmwares answer a command with nothing; that is not an error.
        if isinstance(result, dict):
            self._check(result)
            if isinstance(result.get("dps"), dict):
                self.dps.update({str(k): v for k, v in result["dps"].items()})
                return
        self.dps.update(values)

    def close(self) -> None:
        with self._lock:
            try:
                self._dev.close()
            except Exception:  # noqa: BLE001 - closing must never fail loudly
                pass

    # -------------------------------------------------------------- getters

    def _get(self, dp: str | None) -> Any:
        return None if dp is None else self.dps.get(dp)

    @property
    def is_on(self) -> bool | None:
        val = self._get(self.profile.power_dp)
        return None if val is None else bool(val)

    @property
    def target_temperature(self) -> int | None:
        return self._get(self.profile.target_temp_dp)

    @property
    def current_temperature(self) -> int | None:
        return self._get(self.profile.current_temp_dp)

    @property
    def fahrenheit(self) -> bool:
        return self._get(self.profile.temp_unit_dp) == "F"

    @property
    def temp_range(self) -> tuple[int, int]:
        lo, hi = self.profile.min_temp, self.profile.max_temp
        if self.fahrenheit:
            return round(lo * 9 / 5 + 32), round(hi * 9 / 5 + 32)
        return lo, hi

    @property
    def preset(self) -> str | None:
        return self.profile.presets.get(self._get(self.profile.preset_dp))

    @property
    def preset_options(self) -> list[str]:
        return list(self.profile.presets.values())

    @property
    def is_heating(self) -> bool | None:
        val = self._get(self.profile.action_dp)
        if val is None:
            return None
        return val != self.profile.action_idle_value

    @property
    def child_lock(self) -> bool | None:
        val = self._get(self.profile.child_lock_dp)
        return None if val is None else bool(val)

    @property
    def display_on(self) -> bool | None:
        # inverted: device True means "display off"
        val = self._get(self.profile.display_dp)
        return None if val is None else not val

    @property
    def backlight_on(self) -> bool | None:
        val = self._get(self.profile.backlight_dp)
        return None if val is None else not val

    @property
    def timer(self) -> str | None:
        val = self._get(self.profile.timer_dp)
        if val is None:
            return None
        if self.profile.timer_numeric:
            val = str(val)
            return "cancel" if val == "0" else f"{val}h"
        return str(val)

    @property
    def timer_remaining(self) -> int | None:
        return self._get(self.profile.timer_remaining_dp)

    @property
    def fault_code(self) -> int | None:
        return self._get(self.profile.fault_dp)

    # -------------------------------------------------------------- setters

    def set_power(self, on: bool) -> None:
        self.set_dps({self.profile.power_dp: bool(on)})

    def set_target_temperature(self, value: float) -> None:
        lo, hi = self.temp_range
        self.set_dps(
            {self.profile.target_temp_dp: int(max(lo, min(hi, round(value))))}
        )

    def set_preset(self, preset: str) -> None:
        for dev_val, name in self.profile.presets.items():
            if name == preset:
                self.set_dps({self.profile.preset_dp: dev_val})
                return
        raise BornholmError(f"Unknown preset {preset}")

    def set_child_lock(self, locked: bool) -> None:
        self.set_dps({self.profile.child_lock_dp: bool(locked)})

    def set_display(self, on: bool) -> None:
        self.set_dps({self.profile.display_dp: not on})

    def set_backlight(self, on: bool) -> None:
        self.set_dps({self.profile.backlight_dp: not on})

    def set_timer(self, option: str) -> None:
        if option not in TIMER_OPTIONS:
            raise BornholmError(f"Unknown timer option {option}")
        if self.profile.timer_numeric:
            value = "0" if option == "cancel" else option.removesuffix("h")
        else:
            value = option
        self.set_dps({self.profile.timer_dp: value})


def probe(host: str, device_id: str, local_key: str, protocol_version: str) -> dict:
    """Connect once and return the raw DPs (used by the config flow)."""
    dev = tinytuya.Device(
        device_id,
        address=host,
        local_key=local_key,
        version=float(protocol_version),
        connection_timeout=5,
        connection_retry_limit=1,
        connection_retry_delay=1,
    )
    try:
        result = dev.status()
    finally:
        try:
            dev.close()
        except Exception:  # noqa: BLE001
            pass
    if not isinstance(result, dict) or "Error" in result or "Err" in result:
        raise BornholmError(str(result))
    dps = result.get("dps")
    if not isinstance(dps, dict) or not dps:
        raise BornholmError(f"No DPs returned: {result}")
    return {str(k): v for k, v in dps.items()}
