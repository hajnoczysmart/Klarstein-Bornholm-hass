"""Load const.py and device.py without importing Home Assistant."""

import importlib
import pathlib
import sys
import types

COMPONENT = (
    pathlib.Path(__file__).resolve().parent.parent
    / "custom_components"
    / "klarstein_bornholm"
)

pkg = types.ModuleType("klarstein_bornholm")
pkg.__path__ = [str(COMPONENT)]
sys.modules.setdefault("klarstein_bornholm", pkg)
importlib.import_module("klarstein_bornholm.const")
importlib.import_module("klarstein_bornholm.device")

# cloud.py needs tuya_sharing; use a stub when the SDK is not installed
try:
    import tuya_sharing  # noqa: F401
except ImportError:
    stub = types.ModuleType("tuya_sharing")

    class _Base:
        def __init__(self, *a, **kw):
            pass

    stub.LoginControl = stub.Manager = stub.SharingTokenListener = _Base
    sys.modules["tuya_sharing"] = stub
importlib.import_module("klarstein_bornholm.cloud")
