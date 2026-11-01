# Klarstein Bornholm for Home Assistant

Local (cloud-free) Home Assistant integration for **Klarstein Bornholm** Wi-Fi convection heaters. It talks to the heater directly on your LAN over the Tuya local protocol (via [tinytuya](https://github.com/jasonacox/tinytuya)), so it avoids the "unknown" temperature problem seen with the built-in Tuya integration.

## Supported models

| Model | Tuya product ID |
|---|---|
| Bornholm Smart 1500 | `movachsonarakbut` |
| Bornholm Smart (1 kW, WBR3 module) | `dcxerfhhzu2x1bei` |
| Wonderwall Bornholm / Bornholm IR (GL23040) | `zhepqxx83p6xou61`, `kwicelwvcvgru9vr` |

Other Bornholm Smart variants (e.g. 2 kW) use the same datapoints and are detected automatically. The datapoint mappings are based on the community-verified device files of the [tuya-local](https://github.com/make-all/tuya-local) project.

## Entities

| Entity | Features |
|---|---|
| `climate` | on/off, target temperature (5–45 °C, Wonderwall: 5–50 °C), current temperature, heating/idle, preset (low/high/frost protection, or eco/comfort) |
| `lock` | child lock |
| `select` | shut-off timer (off, 1–24 h) |
| `sensor` | timer time remaining |
| `switch` | display (and backlight on the 1 kW model) |
| `binary_sensor` | fault indicator (with fault code) |

## Installation via HACS

1. HACS → ⋮ (top right) → **Custom repositories**
2. Repository: `https://github.com/hajnoczysmart/Klarstein-Bornholm-hass`, Type: **Integration**
3. Find "Klarstein Bornholm" → **Download**
4. Restart Home Assistant

Manual installation: copy `custom_components/klarstein_bornholm` into your HA `config/custom_components/` folder and restart.

## What you need: IP address, device ID, local key

Pair the heater with the **Smart Life** (or Tuya Smart) app first. If it is currently in the Klarstein app, remove it there and add it again in Smart Life.

**Getting the device ID and local key with `tinytuya`:**

1. Sign up on the [Tuya IoT Platform](https://platform.tuya.com/) and create a Cloud project (data center: *Central Europe* for EU accounts).
2. In the project: **Devices → Link App Account**, then scan the QR code with the Smart Life app (Me → scan icon top right).
3. On a computer:
   ```bash
   pip install tinytuya
   python -m tinytuya wizard
   ```
   Enter the project's Access ID and Secret. The wizard prints `id` and `key` for every device. `key` is the local key.
4. Find the IP address in your router or with `python -m tinytuya scan`. Giving the heater a fixed IP (DHCP reservation) is recommended.

> The local key changes whenever the heater is re-paired in the app. Fetch it again and re-add the integration in that case.

## Configuration

Settings → Devices & services → **Add integration** → *Klarstein Bornholm*

- **IP address**, **Device ID**, **Local key**
- **Protocol version**: leave on *auto*; it tries 3.3, 3.4, 3.5 and 3.1 in turn
- **Model**: leave on *Detect automatically*, or pick one manually if detection is wrong

IP address, protocol version and poll interval can be changed later via the integration's **Configure** button.

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
