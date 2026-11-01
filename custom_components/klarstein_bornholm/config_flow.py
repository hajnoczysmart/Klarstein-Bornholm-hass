"""Config flow for Klarstein Bornholm."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_DEVICE_ID,
    CONF_LOCAL_KEY,
    CONF_MODEL,
    CONF_PROTOCOL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MODEL_AUTO,
    PROFILES,
    PROTOCOL_VERSIONS,
    detect_model,
)
from .device import BornholmError, probe

_LOGGER = logging.getLogger(__name__)

PROTOCOL_AUTO = "auto"
# order to try when the user picks "auto"
AUTO_ORDER = ["3.3", "3.4", "3.5", "3.1"]


async def _async_probe(
    hass: HomeAssistant, host: str, device_id: str, local_key: str, protocol: str
) -> tuple[str, dict]:
    """Return (working protocol version, DPs) or raise BornholmError."""
    versions = AUTO_ORDER if protocol == PROTOCOL_AUTO else [protocol]
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


class BornholmConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID].strip()
            local_key = user_input[CONF_LOCAL_KEY].strip()
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured(updates={CONF_HOST: host})
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
            step_id="user",
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
