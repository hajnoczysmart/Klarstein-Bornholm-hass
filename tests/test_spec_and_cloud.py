"""DP spec handling (Eco, scale, presets) and the cloud device fetch."""

import json
from types import SimpleNamespace

import pytest

from klarstein_bornholm import cloud
from klarstein_bornholm import device as devmod
from klarstein_bornholm.const import (
    MODEL_SMART_1500,
    MODEL_SMART_1KW,
    MODEL_WONDERWALL,
    detect_model,
)
from test_device import FakeTuya, SMART1500


@pytest.fixture(autouse=True)
def fake_tinytuya(monkeypatch):
    monkeypatch.setattr(devmod.tinytuya, "Device", FakeTuya)


def dto(dp, code, vtype, desc):
    return {"dpId": dp, "dpCode": code, "valueType": vtype,
            "valueDesc": json.dumps(desc), "supportLocal": True}


SPEC_2KW = devmod.parse_dp_spec([
    dto(1, "switch", "Boolean", {}),
    dto(2, "temp_set", "Integer", {"min": 50, "max": 350, "scale": 1, "step": 5, "unit": "℃"}),
    dto(3, "temp_current", "Integer", {"min": 0, "max": 500, "scale": 1, "step": 1}),
    dto(4, "level", "Enum", {"range": ["low", "middle", "high"]}),
    dto(5, "eco", "Boolean", {}),
    dto(6, "child_lock", "Boolean", {}),
    dto(104, "light", "Boolean", {}),
])


def make(model, state, spec=None):
    d = devmod.BornholmDevice("1.2.3.4", "id", "key", "3.4", model, spec)
    d._dev.state = dict(state)
    d.update()
    return d


def test_parse_spec():
    assert SPEC_2KW["5"] == {"code": "eco", "type": "Boolean", "values": {}}
    assert SPEC_2KW["4"]["values"]["range"] == ["low", "middle", "high"]
    # broken valueDesc must not crash
    assert devmod.parse_dp_spec([{"dpId": 9, "dpCode": "x", "valueType": "Raw", "valueDesc": "{bad"}]) == {
        "9": {"code": "x", "type": "Raw", "values": {}}}


def test_eco_and_scale_from_spec():
    state = {"1": True, "2": 215, "3": 198, "4": "middle", "5": False, "6": False, "104": False}
    d = make(MODEL_SMART_1500, state, SPEC_2KW)
    assert d.eco_dp == "5" and d.eco_from_spec
    assert d.eco_on is False
    assert d.target_temperature == 21.5 and d.current_temperature == 19.8
    assert d.temp_range == (5.0, 35.0) and d.temp_step == 0.5
    assert d.preset_options == ["low", "middle", "high"] and d.preset == "middle"
    d.set_eco(True)
    d.set_target_temperature(22.5)
    d.set_target_temperature(40)
    d.set_preset("high")
    assert d._dev.sent == [{"5": True}, {"2": 225}, {"2": 350}, {"4": "high"}]


def test_no_spec_falls_back_to_profile_eco_dp():
    d = make(MODEL_SMART_1500, SMART1500)
    assert d.eco_dp == "5" and not d.eco_from_spec and d.has("5")
    d1 = make(MODEL_SMART_1KW, {"1": True, "5": True, "103": "C"})
    assert d1.eco_dp is None  # DP5 is the display on the 1 kW model


def test_spec_without_eco_does_not_guess():
    spec = devmod.parse_dp_spec([dto(1, "switch", "Boolean", {}), dto(5, "sleep", "Boolean", {})])
    d = make(MODEL_SMART_1500, {"1": True, "5": False}, spec)
    assert d.eco_dp is None


def test_mode_enum_with_eco():
    spec = devmod.parse_dp_spec([
        dto(1, "switch", "Boolean", {}),
        dto(4, "level", "Enum", {"range": ["low", "high"]}),
        dto(7, "mode", "Enum", {"range": ["comfort", "eco", "anti-frost"]}),
    ])
    d = make(MODEL_SMART_1500, {"1": True, "4": "low", "7": "eco"}, spec)
    assert d.mode_dp == "7"
    assert list(d.mode_options.values()) == ["comfort", "eco", "anti_frost"]
    assert d.mode == "eco"
    d.set_mode("anti_frost")
    assert d._dev.sent[-1] == {"7": "anti-frost"}


def test_detect_model_with_product_and_spec():
    assert detect_model({}, "dcxerfhhzu2x1bei") == MODEL_SMART_1KW
    assert detect_model({}, "unknown2kw", SPEC_2KW) == MODEL_SMART_1500
    assert detect_model({"1": 1, "19": "1h"}) == MODEL_WONDERWALL
    # 1500 with optional sleep DP 102 must not be mistaken for the 1 kW model
    assert detect_model({"1": 1, "102": False, "104": False}) == MODEL_SMART_1500


def test_fetch_devices(monkeypatch):
    calls = {}

    class Login:
        def qr_code(self, cid, schema, code):
            calls["qr"] = (cid, schema, code)
            return {"success": True, "result": {"qrcode": "TOKEN"}}

        def login_result(self, token, cid, code):
            calls["login"] = (token, code)
            return True, {"terminal_id": "t", "endpoint": "https://e", "t": 1, "uid": "u",
                          "expire_time": 9, "access_token": "a", "refresh_token": "r"}

    class Api:
        def get(self, path):
            assert path == "/v1.0/m/life/devices/heater1/status"
            return {"success": True, "result": {"dpStatusRelationDTOS": [
                dto(5, "eco", "Boolean", {})]}}

    class Mgr:
        def __init__(self, cid, code, term, endpoint, token, listener):
            calls["mgr"] = (code, term, endpoint, token["access_token"])
            self.customer_api = Api()
            self.device_map = {}

        def update_device_cache(self):
            mk = lambda **kw: SimpleNamespace(**kw)
            self.device_map = {
                "plug": mk(id="plug", name="Plug", local_key="k2", category="cz",
                           product_id="p", product_name="Plug", online=True, sub=False),
                "heater1": mk(id="heater1", name="Bornholm", local_key="k1", category="qn",
                              product_id="pid2kw", product_name="Bornholm 2000", online=True, sub=False),
                "ble": mk(id="ble", name="BLE thing", local_key="", category="x",
                          product_id="", product_name="", online=True, sub=False),
            }

    monkeypatch.setattr(cloud, "LoginControl", Login)
    monkeypatch.setattr(cloud, "Manager", Mgr)
    token = cloud.get_qr_token("CODE")
    assert token == "TOKEN" and cloud.qr_payload(token) == "tuyaSmart--qrLogin?token=TOKEN"
    devs = cloud.fetch_devices("CODE", token)
    assert [d["id"] for d in devs] == ["heater1", "plug"]  # heater first, BLE skipped
    assert devs[0]["dp_spec"]["5"]["code"] == "eco" and devs[0]["local_key"] == "k1"
    assert calls["mgr"] == ("CODE", "t", "https://e", "a")


def test_cloud_errors(monkeypatch):
    class Login:
        def qr_code(self, *a):
            return {"success": False, "msg": "invalid user code"}

        def login_result(self, *a):
            return False, {"msg": "not scanned"}

    monkeypatch.setattr(cloud, "LoginControl", Login)
    with pytest.raises(cloud.CloudError, match="invalid user code"):
        cloud.get_qr_token("bad")
    with pytest.raises(cloud.CloudError, match="not scanned"):
        cloud.fetch_devices("c", "t")
