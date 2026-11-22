"""One-off Tuya cloud login used only during setup.

The user logs in with the Tuya Smart / Smart Life app (user code + QR scan).
We read the device list (ID, local key, product ID) and each heater's DP spec,
then forget the session. Normal operation is fully local.
"""

from __future__ import annotations

import logging
from typing import Any

from tuya_sharing import LoginControl, Manager, SharingTokenListener

from .const import TUYA_CLIENT_ID, TUYA_SCHEMA
from .device import parse_dp_spec

_LOGGER = logging.getLogger(__name__)


class CloudError(Exception):
    """Login or API failure; str() is the message from Tuya."""


class _NoopTokenListener(SharingTokenListener):
    def update_token(self, token_info: dict[str, Any]) -> None:
        """Tokens are not stored; nothing to do."""


def get_qr_token(user_code: str) -> str:
    """Ask Tuya for a QR login token (blocking)."""
    response = LoginControl().qr_code(TUYA_CLIENT_ID, TUYA_SCHEMA, user_code)
    if not response.get("success"):
        raise CloudError(response.get("msg") or str(response))
    return response["result"]["qrcode"]


def qr_payload(token: str) -> str:
    """Text encoded in the QR code that the Tuya app scans."""
    return f"tuyaSmart--qrLogin?token={token}"


def fetch_devices(user_code: str, token: str) -> list[dict[str, Any]]:
    """Finish the QR login and return the account's devices (blocking)."""
    ok, info = LoginControl().login_result(token, TUYA_CLIENT_ID, user_code)
    if not ok:
        raise CloudError(info.get("msg") or "QR code not scanned or confirmed yet")

    manager = Manager(
        TUYA_CLIENT_ID,
        user_code,
        info["terminal_id"],
        info["endpoint"],
        {
            "t": info["t"],
            "uid": info["uid"],
            "expire_time": info["expire_time"],
            "access_token": info["access_token"],
            "refresh_token": info["refresh_token"],
        },
        _NoopTokenListener(),
    )
    manager.update_device_cache()

    devices = []
    for dev in manager.device_map.values():
        local_key = getattr(dev, "local_key", "") or ""
        if not local_key or getattr(dev, "sub", False):
            continue  # sub-devices / BLE devices cannot be controlled locally
        spec: dict = {}
        try:
            resp = manager.customer_api.get(f"/v1.0/m/life/devices/{dev.id}/status")
            if resp.get("success"):
                spec = parse_dp_spec(resp["result"].get("dpStatusRelationDTOS"))
        except Exception as err:  # noqa: BLE001 - spec is optional
            _LOGGER.debug("Could not read DP spec of %s: %s", dev.id, err)
        devices.append(
            {
                "id": dev.id,
                "name": getattr(dev, "name", dev.id),
                "local_key": local_key,
                "category": getattr(dev, "category", ""),
                "product_id": getattr(dev, "product_id", ""),
                "product_name": getattr(dev, "product_name", ""),
                "online": getattr(dev, "online", None),
                "dp_spec": spec,
            }
        )
    # heaters ("qn") first, then by name
    devices.sort(key=lambda d: (d["category"] != "qn", d["name"].lower()))
    return devices
