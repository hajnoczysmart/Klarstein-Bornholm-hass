"""Local Tuya communication with a Klarstein Bornholm heater.

This module has no Home Assistant imports so it can be tested on its own.
All methods are blocking; Home Assistant calls them in an executor.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import fields, replace
from typing import Any

import tinytuya

from .const import PROFILES, TIMER_OPTIONS, ModelProfile

_LOGGER = logging.getLogger(__name__)


class BornholmError(Exception):
    """Raised when the heater cannot be reached or rejects a command."""


def slug(value: Any) -> str:
    """Turn a device enum value into a translation-friendly key."""
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_") or "unknown"


def parse_dp_spec(raw: list[dict] | None) -> dict[str, dict]:
    """Convert Tuya's dpStatusRelationDTOS list into {dp_id: spec}."""
    spec: dict[str, dict] = {}
    for item in raw or []:
        dp_id = item.get("dpId")
        if dp_id is None:
            continue
        desc = item.get("valueDesc") or "{}"
        try:
            values = json.loads(desc) if isinstance(desc, str) else dict(desc)
        except (ValueError, TypeError):
            values = {}
        spec[str(dp_id)] = {
            "code": item.get("dpCode") or item.get("statusCode") or "",
            "type": item.get("valueType") or "",
            "values": values if isinstance(values, dict) else {},
        }
    return spec


class BornholmDevice:
    """Thin wrapper around tinytuya with Bornholm-specific value mapping."""

    def __init__(
        self,
        host: str,
        device_id: str,
        local_key: str,
        protocol_version: str,
        model: str,
        dp_spec: dict[str, dict] | None = None,
    ) -> None:
        self.profile: ModelProfile = PROFILES[model]
        self.spec: dict[str, dict] = dp_spec or {}
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
        self._setup_from_spec()

    # ------------------------------------------------------------ DP spec

    def _setup_from_spec(self) -> None:
        # The device's own DP spec wins over the profile: if it names a DP
        # "eco", any other feature the profile mapped to that DP is dropped.
        spec_eco = next(
            (
                dp
                for dp, s in sorted(self.spec.items(), key=lambda kv: int(kv[0]))
                if s["type"] == "Boolean" and "eco" in s["code"].lower()
            ),
            None,
        )
        if spec_eco:
            core = {"power_dp", "target_temp_dp", "current_temp_dp"}
            clash = {
                f.name: None
                for f in fields(self.profile)
                if f.name.endswith("_dp")
                and f.name not in core | {"eco_dp"}
                and getattr(self.profile, f.name) == spec_eco
            }
            self.profile = replace(self.profile, eco_dp=spec_eco, **clash)
        p = self.profile
        # presets: extend/replace with the values the device really supports
        self.presets: dict[Any, str] = dict(p.presets)
        rng = self._enum_range(p.preset_dp)
        if rng:
            self.presets = {v: p.presets.get(v, slug(v)) for v in rng}

        used = {
            p.power_dp, p.target_temp_dp, p.current_temp_dp, p.preset_dp,
            p.action_dp, p.child_lock_dp, p.display_dp, p.backlight_dp,
            p.timer_dp, p.timer_remaining_dp, p.fault_dp, p.temp_unit_dp,
        }

        # Eco as a boolean DP
        self.eco_dp: str | None = spec_eco
        self.eco_from_spec = spec_eco is not None
        if not self.spec:
            self.eco_dp = p.eco_dp
        if self.eco_dp:
            used.add(self.eco_dp)

        # Eco as one option of another enum DP (e.g. "mode": comfort/eco/anti-frost)
        self.mode_dp: str | None = None
        self.mode_options: dict[Any, str] = {}
        for dp, s in sorted(self.spec.items(), key=lambda kv: int(kv[0])):
            rng = self._enum_range(dp)
            if dp not in used and rng and any("eco" in str(v).lower() for v in rng):
                self.mode_dp = dp
                self.mode_options = {v: slug(v) for v in rng}
                break

    def _enum_range(self, dp: str | None) -> list | None:
        s = self.spec.get(dp or "")
        if s and s["type"] == "Enum" and isinstance(s["values"].get("range"), list):
            return s["values"]["range"]
        return None

    def _scale(self, dp: str) -> int:
        s = self.spec.get(dp)
        if s and s["type"] == "Integer":
            try:
                return int(s["values"].get("scale", 0))
            except (TypeError, ValueError):
                return 0
        return 0

    def _to_ha(self, dp: str, raw: Any) -> float | None:
        if raw is None:
            return None
        scale = self._scale(dp)
        return raw / 10**scale if scale else raw

    def _to_device(self, dp: str, value: float) -> int:
        return int(round(value * 10 ** self._scale(dp)))

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

    def has(self, dp: str | None) -> bool:
        """True if the heater reports this DP (or the cloud spec lists it)."""
        return dp is not None and (dp in self.dps or dp in self.spec)

    @property
    def is_on(self) -> bool | None:
        val = self._get(self.profile.power_dp)
        return None if val is None else bool(val)

    @property
    def target_temperature(self) -> float | None:
        dp = self.profile.target_temp_dp
        return self._to_ha(dp, self._get(dp))

    @property
    def current_temperature(self) -> float | None:
        dp = self.profile.current_temp_dp
        return self._to_ha(dp, self._get(dp))

    @property
    def fahrenheit(self) -> bool:
        return self._get(self.profile.temp_unit_dp) == "F"

    @property
    def temp_range(self) -> tuple[float, float]:
        dp = self.profile.target_temp_dp
        vals = self.spec.get(dp, {}).get("values", {})
        if not self.fahrenheit and "min" in vals and "max" in vals:
            return self._to_ha(dp, vals["min"]), self._to_ha(dp, vals["max"])
        lo, hi = self.profile.min_temp, self.profile.max_temp
        if self.fahrenheit:
            return round(lo * 9 / 5 + 32), round(hi * 9 / 5 + 32)
        return lo, hi

    @property
    def temp_step(self) -> float:
        dp = self.profile.target_temp_dp
        step = self.spec.get(dp, {}).get("values", {}).get("step", 1)
        try:
            return self._to_ha(dp, int(step)) or 1
        except (TypeError, ValueError):
            return 1

    @property
    def preset(self) -> str | None:
        return self.presets.get(self._get(self.profile.preset_dp))

    @property
    def preset_options(self) -> list[str]:
        return list(self.presets.values())

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
    def eco_on(self) -> bool | None:
        val = self._get(self.eco_dp)
        return None if val is None else bool(val)

    @property
    def mode(self) -> str | None:
        return self.mode_options.get(self._get(self.mode_dp))

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
        dp = self.profile.target_temp_dp
        self.set_dps({dp: self._to_device(dp, max(lo, min(hi, value)))})

    def set_preset(self, preset: str) -> None:
        for dev_val, name in self.presets.items():
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

    def set_eco(self, on: bool) -> None:
        if not self.eco_dp:
            raise BornholmError("This heater has no Eco DP")
        self.set_dps({self.eco_dp: bool(on)})

    def set_mode(self, option: str) -> None:
        for dev_val, name in self.mode_options.items():
            if name == option:
                self.set_dps({self.mode_dp: dev_val})
                return
        raise BornholmError(f"Unknown mode {option}")

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


def find_on_lan(device_id: str) -> dict:
    """Look for the heater's UDP broadcast on the LAN (takes up to ~20 s)."""
    try:
        found = tinytuya.find_device(dev_id=device_id)
    except OSError as err:
        _LOGGER.debug("LAN scan failed: %s", err)
        return {}
    if not found or not found.get("ip"):
        return {}
    return {"ip": found["ip"], "version": str(found.get("version") or "")}
