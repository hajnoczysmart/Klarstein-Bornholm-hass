"""Config flow for Klarstein Bornholm.

Two ways to set up a heater:
  * cloud-assisted: log in once with the Tuya Smart / Smart Life app (user code
    + QR scan); device ID, local key and DP spec are fetched, the IP address and
    protocol version are found on the LAN;
  * manual: enter IP address, device ID and local key yourself.
"""

from __future__ import annotations

import logging
from typing import Any

try:  # Home Assistant 2026.9+ ships probatio instead of voluptuous
    import probatio as vol
except ImportError:  # pragma: no cover - older Home Assistant
    import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    QrCodeSelector,
    QrCodeSelectorConfig,
    QrErrorCorrectionLevel,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_DEVICE_ID,
    CONF_DP_SPEC,
    CONF_LOCAL_KEY,
    CONF_MODEL,
    CONF_PRODUCT_ID,
    CONF_PROTOCOL,
    CONF_SCAN_INTERVAL,
    CONF_USER_CODE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MODEL_AUTO,
    PROFILES,
    PROTOCOL_VERSIONS,
    detect_model,
)
from .device import BornholmError, find_on_lan, probe

_LOGGER = logging.getLogger(__name__)

PROTOCOL_AUTO = "auto"
# order to try when the protocol version is unknown
AUTO_ORDER = ["3.3", "3.4", "3.5", "3.1"]


async def _async_probe(
    hass: HomeAssistant, host: str, device_id: str, local_key: str, protocol: str
) -> tuple[str, dict]:
    """Return (working protocol version, DPs) or raise BornholmError."""
    if protocol in (PROTOCOL_AUTO, "", None):
        versions = AUTO_ORDER
    else:
        versions = [protocol] + [v for v in AUTO_ORDER if v != protocol]
    last_err: Exception | None = None
    for version in versions:
        try:
            dps = await hass.async_add_executor_job(
                probe, host, device_id, local_key, version
            )
        except BornholmError as err:
            _LOGGER.debug("Protocol %s failed: %s", version, err)
            last_err = err
            continue
        return version, dps
    raise BornholmError(str(last_err))


def _model_selector(include_auto: bool) -> SelectSelector:
    options = ([MODEL_AUTO] if include_auto else []) + list(PROFILES)
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            translation_key="model",
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _protocol_selector(include_auto: bool) -> SelectSelector:
    options = ([PROTOCOL_AUTO] if include_auto else []) + PROTOCOL_VERSIONS
    return SelectSelector(
        SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
    )


def _qr_schema(token: str) -> vol.Schema:
    from .cloud import qr_payload

    return vol.Schema(
        {
            vol.Optional("qr"): QrCodeSelector(
                QrCodeSelectorConfig(
                    data=qr_payload(token),
                    scale=5,
                    error_correction_level=QrErrorCorrectionLevel.QUARTILE,
                )
            )
        }
    )


class BornholmConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._user_code: str | None = None
        self._qr_token: str | None = None
        self._cloud_devices: list[dict[str, Any]] = []
        self._device: dict[str, Any] = {}
        self._found: dict[str, Any] = {}

    # ------------------------------------------------------------ entry menu

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["cloud", "manual"])

    # --------------------------------------------------------- cloud-assisted

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        from .cloud import CloudError, get_qr_token

        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        if user_input is not None:
            code = user_input[CONF_USER_CODE].strip()
            try:
                self._qr_token = await self.hass.async_add_executor_job(
                    get_qr_token, code
                )
            except (CloudError, OSError, KeyError, ValueError) as err:
                _LOGGER.warning("Tuya QR request failed: %s", err)
                errors["base"] = "cloud_error"
                placeholders["error"] = f"\n\nTuya: {err}"
            else:
                self._user_code = code
                return await self.async_step_scan()

        return self.async_show_form(
            step_id="cloud",
            data_schema=vol.Schema(
                {vol.Required(CONF_USER_CODE, default=self._user_code or ""): str}
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_scan(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        from .cloud import CloudError, fetch_devices, get_qr_token

        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        if user_input is not None:
            try:
                self._cloud_devices = await self.hass.async_add_executor_job(
                    fetch_devices, self._user_code, self._qr_token
                )
            except (CloudError, OSError, KeyError, ValueError) as err:
                _LOGGER.warning("Tuya login failed: %s", err)
                errors["base"] = "login_failed"
                placeholders["error"] = f"\n\nTuya: {err}"
                try:  # tokens are single-use: get a fresh QR code
                    self._qr_token = await self.hass.async_add_executor_job(
                        get_qr_token, self._user_code
                    )
                except (CloudError, OSError, KeyError, ValueError):
                    return self.async_abort(reason="cloud_error")
            else:
                if not self._cloud_devices:
                    return self.async_abort(reason="no_devices")
                return await self.async_step_pick()

        return self.async_show_form(
            step_id="scan",
            data_schema=_qr_schema(self._qr_token or ""),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._device = next(
                d for d in self._cloud_devices if d["id"] == user_input[CONF_DEVICE_ID]
            )
            dev = self._device
            model = detect_model({}, dev["product_id"], dev["dp_spec"])
            await self.async_set_unique_id(dev["id"])
            # Already set up: refresh key / DP spec (e.g. after re-pairing)
            self._abort_if_unique_id_configured(
                updates={
                    CONF_LOCAL_KEY: dev["local_key"],
                    CONF_PRODUCT_ID: dev["product_id"],
                    CONF_DP_SPEC: dev["dp_spec"],
                    CONF_MODEL: model,
                }
            )
            return await self.async_step_search()

        configured = self._async_current_ids(include_ignore=False)
        options = [
            SelectOptionDict(
                value=d["id"],
                label=f"{d['name']} ({d['product_name'] or d['category']})"
                + ("" if d["online"] is not False else " - offline")
                + (" - already added" if d["id"] in configured else ""),
            )
            for d in self._cloud_devices
        ]
        return self.async_show_form(
            step_id="pick",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_DEVICE_ID, default=options[0]["value"]
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=options, mode=SelectSelectorMode.LIST
                        )
                    )
                }
            ),
        )

    async def async_step_search(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Find the heater's LAN IP from its UDP broadcast, then connect."""
        if user_input is None:
            return self.async_show_form(
                step_id="search",
                data_schema=vol.Schema({}),
                description_placeholders={"name": self._device["name"]},
                last_step=False,
            )
        self._found = await self.hass.async_add_executor_job(
            find_on_lan, self._device["id"]
        )
        if self._found.get("ip"):
            try:
                return await self._async_create_cloud_entry(
                    self._found["ip"], self._found.get("version") or PROTOCOL_AUTO
                )
            except BornholmError as err:
                _LOGGER.debug("Found on LAN but could not connect: %s", err)
        return await self.async_step_host()

    async def async_step_host(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the IP if the LAN scan did not find (or reach) the heater."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                return await self._async_create_cloud_entry(
                    user_input[CONF_HOST].strip(), user_input[CONF_PROTOCOL]
                )
            except BornholmError:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="host",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=self._found.get("ip") or ""): str,
                    vol.Required(
                        CONF_PROTOCOL,
                        default=self._found.get("version") or PROTOCOL_AUTO,
                    ): _protocol_selector(True),
                }
            ),
            errors=errors,
            description_placeholders={"name": self._device["name"]},
        )

    async def _async_create_cloud_entry(
        self, host: str, protocol: str
    ) -> ConfigFlowResult:
        dev = self._device
        version, dps = await _async_probe(
            self.hass, host, dev["id"], dev["local_key"], protocol
        )
        model = detect_model(dps, dev["product_id"], dev["dp_spec"])
        _LOGGER.debug("Bornholm %s: DPs %s spec %s -> %s", dev["id"], dps, dev["dp_spec"], model)
        return self.async_create_entry(
            title=dev["name"] or f"Klarstein {PROFILES[model].name}",
            data={
                CONF_HOST: host,
                CONF_DEVICE_ID: dev["id"],
                CONF_LOCAL_KEY: dev["local_key"],
                CONF_PROTOCOL: version,
                CONF_MODEL: model,
                CONF_PRODUCT_ID: dev["product_id"],
                CONF_DP_SPEC: dev["dp_spec"],
            },
        )

    # ----------------------------------------------------------------- manual

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID].strip()
            local_key = user_input[CONF_LOCAL_KEY].strip()
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured(
                updates={CONF_HOST: host, CONF_LOCAL_KEY: local_key}
            )
            try:
                version, dps = await _async_probe(
                    self.hass, host, device_id, local_key, user_input[CONF_PROTOCOL]
                )
            except BornholmError:
                errors["base"] = "cannot_connect"
            else:
                model = user_input[CONF_MODEL]
                if model == MODEL_AUTO:
                    model = detect_model(dps)
                _LOGGER.debug("Bornholm DPs: %s -> model %s", dps, model)
                return self.async_create_entry(
                    title=f"Klarstein {PROFILES[model].name}",
                    data={
                        CONF_HOST: host,
                        CONF_DEVICE_ID: device_id,
                        CONF_LOCAL_KEY: local_key,
                        CONF_PROTOCOL: version,
                        CONF_MODEL: model,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_DEVICE_ID): str,
                vol.Required(CONF_LOCAL_KEY): str,
                vol.Required(CONF_PROTOCOL, default=PROTOCOL_AUTO): _protocol_selector(
                    True
                ),
                vol.Required(CONF_MODEL, default=MODEL_AUTO): _model_selector(True),
            }
        )
        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return BornholmOptionsFlow()


class BornholmOptionsFlow(OptionsFlow):
    """Change IP address, protocol version or poll interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.config_entry
        current = {**entry.data, **entry.options}
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await _async_probe(
                    self.hass,
                    user_input[CONF_HOST].strip(),
                    entry.data[CONF_DEVICE_ID],
                    entry.data[CONF_LOCAL_KEY],
                    user_input[CONF_PROTOCOL],
                )
            except BornholmError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    data={**user_input, CONF_HOST: user_input[CONF_HOST].strip()}
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=current[CONF_HOST]): str,
                vol.Required(
                    CONF_PROTOCOL, default=current[CONF_PROTOCOL]
                ): _protocol_selector(False),
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
