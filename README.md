# Klarstein Bornholm for Home Assistant

Local (cloud-free) Home Assistant integration for **Klarstein Bornholm** Wi-Fi convection heaters. It talks to the heater directly on your LAN over the Tuya local protocol (via [tinytuya](https://github.com/jasonacox/tinytuya)), so it avoids the "unknown" temperature problem seen with the built-in Tuya integration.

## Supported models

| Model | Tuya product ID |
|---|---|
| Bornholm Smart 1500 | `movachsonarakbut` |
| Bornholm Smart (WBR3 module, 1 kW / 2 kW) | `dcxerfhhzu2x1bei` |
| Wonderwall Bornholm / Bornholm IR (GL23040) | `zhepqxx83p6xou61`, `kwicelwvcvgru9vr` |

Other Bornholm Smart variants (e.g. 2 kW) use the same datapoints and are detected automatically. With cloud-assisted setup the integration also reads the heater's datapoint description from Tuya, so features such as **Eco mode**, the exact temperature range and extra heat levels are picked up automatically. The datapoint mappings are based on the community-verified device files of the [tuya-local](https://github.com/make-all/tuya-local) project.

## Entities

| Entity | Features |
|---|---|
| `climate` | on/off, target temperature (5–45 °C, Wonderwall: 5–50 °C), current temperature, heating/idle, preset (low/high/frost protection, or eco/comfort) |
| `lock` | child lock |
| `select` | heating level (low/high), shut-off timer (off, 1–24 h) |
| `sensor` | timer time remaining |
| `switch` | power on/off, Eco mode, display or backlight (depending on model) |
| `select` (mode) | operating mode, on heaters that report Eco as part of a mode list |
| `binary_sensor` | fault indicator (with fault code) |

## Installation via HACS

1. HACS → ⋮ (top right) → **Custom repositories**
2. Repository: `https://github.com/hajnoczysmart/Klarstein-Bornholm-hass`, Type: **Integration**
3. Find "Klarstein Bornholm" → **Download**
4. Restart Home Assistant

Manual installation: copy `custom_components/klarstein_bornholm` into your HA `config/custom_components/` folder and restart.

## Setup

Pair the heater with the **Tuya Smart** or **Smart Life** app first.

Settings → Devices & services → **Add integration** → *Klarstein Bornholm*, then pick one of:

### Log in with the Tuya app (recommended)

1. In the Tuya Smart / Smart Life app: **Me → Settings (⚙) → Account and Security**, copy the **User Code** at the bottom (case-sensitive).
2. Enter the user code. A QR code is shown.
3. In the app, tap the scan icon on the **Me** tab, scan the QR code and confirm the login.
4. Pick your heater from the list.
5. Home Assistant listens on your network for up to 20 seconds to find the heater's IP address and protocol version. If it can't, you are asked for the IP address.

The cloud login is used only during setup to read the device ID, local key and datapoint description; nothing is stored and normal operation is fully local. If you re-pair the heater in the app (which changes its local key), simply run the setup again: the existing entry is updated.

### Manual setup

Enter the **IP address**, **device ID** and **local key** yourself (e.g. from `python -m tinytuya wizard`). Leave **Protocol version** on *auto* and **Model** on *Detect automatically*. Eco mode is offered on DP 5 when the heater reports it; for full auto-detection use the app login above.

### Afterwards

IP address, protocol version and poll interval can be changed via the integration's **Configure** button. Giving the heater a fixed IP (DHCP reservation) is recommended.

## Troubleshooting

- **"Could not connect"**: Tuya devices usually accept only one local connection at a time. Close the phone app and disable the built-in Tuya / Tuya Local / LocalTuya integration for the same device.
- **Wrong or missing entities**: download diagnostics (integration → device → ⋮ → *Download diagnostics*) and open an issue with it. The local key is redacted.
- Debug logging:
  ```yaml
  logger:
    logs:
      custom_components.klarstein_bornholm: debug
  ```

## License

MIT
