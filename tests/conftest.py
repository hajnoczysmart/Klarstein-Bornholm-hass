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
