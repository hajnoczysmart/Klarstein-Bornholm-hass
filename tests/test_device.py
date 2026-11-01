"""Tests for the Bornholm DP mapping, using a fake tinytuya device."""

import pytest

from klarstein_bornholm import device as devmod
from klarstein_bornholm.const import (
    MODEL_SMART_1500,
    MODEL_SMART_1KW,
    MODEL_WONDERWALL,
    detect_model,
)


class FakeTuya:
    def __init__(self, dev_id, address=None, local_key="", version=3.1, **kw):
        self.version = version
        self.state = {}
        self.sent = []
        self.fail = False

    def status(self):
        if self.fail:
            return {"Error": "Network Error: Unable to Connect", "Err": "901"}
        return {"devId": "x", "dps": dict(self.state)}

    def set_multiple_values(self, data):
        self.sent.append(dict(data))
        self.state.update(data)
        return {"dps": dict(data)}

    def close(self):
        pass


@pytest.fixture(autouse=True)
def fake_tinytuya(monkeypatch):
    monkeypatch.setattr(devmod.tinytuya, "Device", FakeTuya)


def make(model, state):
    dev = devmod.BornholmDevice("1.2.3.4", "id", "key", "3.3", model)
    dev._dev.state = dict(state)
    dev.update()
    return dev


SMART1500 = {"1": True, "2": 22, "3": 19, "4": "high", "6": False, "10": "0",
             "11": 0, "12": 0, "101": True, "104": False, "5": False}
SMART1KW = {"1": False, "2": 20, "3": 18, "4": "low", "5": True, "6": True,
            "10": "3", "11": 170, "12": 0, "101": False, "102": False, "103": "C"}
WONDERWALL = {"1": True, "2": 24, "3": 21, "6": True, "7": False, "10": False,
              "11": "standby", "19": "2h", "20": 95}


def test_detect_model():
    assert detect_model(SMART1500) == MODEL_SMART_1500
    assert detect_model(SMART1KW) == MODEL_SMART_1KW
    assert detect_model(WONDERWALL) == MODEL_WONDERWALL


def test_protocol_version_is_float():
    dev = make(MODEL_SMART_1500, SMART1500)
    assert dev._dev.version == 3.3


def test_smart1500_read():
    d = make(MODEL_SMART_1500, SMART1500)
    assert d.is_on is True
    assert d.target_temperature == 22
    assert d.current_temperature == 19
    assert d.preset == "high"
    assert d.preset_options == ["low", "high", "away"]
    assert d.is_heating is True
    assert d.child_lock is False
    assert d.display_on is True  # DP104 False = display on
    assert d.timer == "cancel"
    assert d.fault_code == 0
    assert d.temp_range == (5, 45)


def test_smart1500_write():
    d = make(MODEL_SMART_1500, SMART1500)
    d.set_target_temperature(30.4)
    d.set_target_temperature(99)
    d.set_preset("away")
    d.set_timer("5h")
    d.set_timer("cancel")
    d.set_display(False)
    d.set_power(False)
    assert d._dev.sent == [
        {"2": 30}, {"2": 45}, {"4": "empty"}, {"10": "5"}, {"10": "0"},
        {"104": True}, {"1": False},
    ]
    assert d.is_on is False and d.display_on is False


def test_smart1kw_fahrenheit_and_backlight():
    d = make(MODEL_SMART_1KW, SMART1KW)
    assert d.timer == "3h"
    assert d.backlight_on is True
    assert d.display_on is False
    assert d.preset_options == ["low", "high"]
    d._dev.state["103"] = "F"
    d.update()
    assert d.fahrenheit and d.temp_range == (41, 113)
    d.set_target_temperature(200)
    assert d._dev.sent[-1] == {"2": 113}


def test_wonderwall():
    d = make(MODEL_WONDERWALL, WONDERWALL)
    assert d.preset == "eco"
    assert d.is_heating is False  # "standby"
    assert d.timer == "2h"
    assert d.timer_remaining == 95
    assert d.temp_range == (5, 50)
    d.set_preset("comfort")
    d.set_timer("cancel")
    d.set_child_lock(True)
    assert d._dev.sent == [{"6": False}, {"19": "cancel"}, {"7": True}]
    d._dev.state["11"] = "heating"
    d.update()
    assert d.is_heating is True


def test_errors():
    d = make(MODEL_SMART_1500, SMART1500)
    d._dev.fail = True
    with pytest.raises(devmod.BornholmError):
        d.update()
    with pytest.raises(devmod.BornholmError):
        d.set_preset("turbo")
    with pytest.raises(devmod.BornholmError):
        d.set_timer("25h")


def test_command_without_reply_keeps_state():
    d = make(MODEL_SMART_1500, SMART1500)
    d._dev.set_multiple_values = lambda data: None
    d.set_target_temperature(25)
    assert d.target_temperature == 25


def test_probe(monkeypatch):
    class P(FakeTuya):
        def status(self):
            return {"dps": {1: True, "2": 21}}
    monkeypatch.setattr(devmod.tinytuya, "Device", P)
    assert devmod.probe("h", "i", "k", "3.4") == {"1": True, "2": 21}

    class E(FakeTuya):
        def status(self):
            return {"Error": "Check device key or version", "Err": "914"}
    monkeypatch.setattr(devmod.tinytuya, "Device", E)
    with pytest.raises(devmod.BornholmError):
        devmod.probe("h", "i", "k", "3.4")
