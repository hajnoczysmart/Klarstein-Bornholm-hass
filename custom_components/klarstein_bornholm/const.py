"""Constants and model profiles for the Klarstein Bornholm integration.

The datapoint (DP) maps below come from the community-verified device files of
the tuya-local project (make-all/tuya-local):
  - klarstein_bornholmsmart1500_heater.yaml
  - klarstein_bornholm_smart_heater.yaml
  - klarstein_wonderwall_bornholm.yaml
"""

from __future__ import annotations

from dataclasses import dataclass, field

DOMAIN = "klarstein_bornholm"

CONF_DEVICE_ID = "device_id"
CONF_LOCAL_KEY = "local_key"
CONF_PROTOCOL = "protocol_version"
CONF_MODEL = "model"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_PRODUCT_ID = "product_id"
CONF_DP_SPEC = "dp_spec"
CONF_USER_CODE = "user_code"

DEFAULT_PROTOCOL = "3.3"
PROTOCOL_VERSIONS = ["3.1", "3.2", "3.3", "3.4", "3.5"]
DEFAULT_SCAN_INTERVAL = 15  # seconds

# Tuya "device sharing" login, as used by Home Assistant's Tuya integration
TUYA_CLIENT_ID = "HA_3y9q4ak7g4ephrvke"
TUYA_SCHEMA = "haauthorize"

MODEL_AUTO = "auto"
MODEL_SMART_1500 = "bornholm_smart_1500"
MODEL_SMART_1KW = "bornholm_smart_1kw"
MODEL_WONDERWALL = "wonderwall_bornholm"

TIMER_OPTIONS = ["cancel"] + [f"{h}h" for h in range(1, 25)]


@dataclass(frozen=True)
class ModelProfile:
    """Describes how one Bornholm variant maps its features to Tuya DPs."""

    name: str
    power_dp: str = "1"
    target_temp_dp: str = "2"
    current_temp_dp: str = "3"
    min_temp: int = 5
    max_temp: int = 45
    # preset: DP id + {device value: HA preset key}
    preset_dp: str | None = None
    presets: dict = field(default_factory=dict)
    # heating action: DP id + value that means "idle"
    action_dp: str | None = None
    action_idle_value: object = False
    child_lock_dp: str | None = None
    # display DPs are inverted on these heaters: True on the device = display off
    display_dp: str | None = None
    backlight_dp: str | None = None
    timer_dp: str | None = None
    # True: the device uses "0".."24"; False: "cancel","1h".."24h"
    timer_numeric: bool = True
    timer_remaining_dp: str | None = None
    fault_dp: str | None = None
    temp_unit_dp: str | None = None
    # boolean Eco DP, used when the cloud DP spec is not available
    eco_dp: str | None = None


PROFILES: dict[str, ModelProfile] = {
    MODEL_SMART_1500: ModelProfile(
        name="Bornholm Smart",
        max_temp=45,
        preset_dp="4",
        presets={"low": "low", "high": "high", "empty": "away"},
        action_dp="101",
        action_idle_value=False,
        child_lock_dp="6",
        display_dp="104",
        timer_dp="10",
        timer_numeric=True,
        timer_remaining_dp="11",
        fault_dp="12",
        eco_dp="5",
    ),
    # Product dcxerfhhzu2x1bei (WBR3 module, 1 kW and 2 kW). DP 5 is Eco, as
    # the Tuya cloud DP spec says and confirmed on a 2 kW unit (tuya-local
    # lists it as the display).
    MODEL_SMART_1KW: ModelProfile(
        name="Bornholm Smart (WBR3)",
        max_temp=45,
        preset_dp="4",
        presets={"low": "low", "high": "high"},
        action_dp="101",
        action_idle_value=False,
        child_lock_dp="6",
        eco_dp="5",
        backlight_dp="102",
        timer_dp="10",
        timer_numeric=True,
        timer_remaining_dp="11",
        fault_dp="12",
        temp_unit_dp="103",
    ),
    MODEL_WONDERWALL: ModelProfile(
        name="Wonderwall Bornholm",
        max_temp=50,
        preset_dp="6",
        presets={True: "eco", False: "comfort"},
        action_dp="11",
        action_idle_value="standby",
        child_lock_dp="7",
        display_dp="10",
        timer_dp="19",
        timer_numeric=False,
        timer_remaining_dp="20",
    ),
}

# Tuya product IDs known from tuya-local
PRODUCT_IDS: dict[str, str] = {
    "movachsonarakbut": MODEL_SMART_1500,
    "dcxerfhhzu2x1bei": MODEL_SMART_1KW,
    "zhepqxx83p6xou61": MODEL_WONDERWALL,
    "kwicelwvcvgru9vr": MODEL_WONDERWALL,
}


def detect_model(
    status: dict, product_id: str | None = None, dp_spec: dict | None = None
) -> str:
    """Guess the variant from product id, cloud DP spec or reported DPs."""
    if product_id and product_id in PRODUCT_IDS:
        return PRODUCT_IDS[product_id]
    dps = {str(k) for k in status} | {str(k) for k in (dp_spec or {})}
    if "19" in dps or "20" in dps:
        return MODEL_WONDERWALL
    if "104" in dps:
        return MODEL_SMART_1500
    if "103" in dps:
        return MODEL_SMART_1KW
    if "7" in dps and "4" not in dps:
        return MODEL_WONDERWALL
    return MODEL_SMART_1500
