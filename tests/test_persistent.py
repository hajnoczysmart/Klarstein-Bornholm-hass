"""One long-lived connection per heater instead of one per poll."""

import time

import pytest

from fake_tuya import FakeTuyaDevice
from klarstein_bornholm import device as devmod

KEY = "1111222233334444"


@pytest.fixture(scope="module")
def heater():
    dev = FakeTuyaDevice("127.0.0.40", "bfPERSIST", KEY,
                         {"1": True, "2": 22, "3": 20, "4": "high", "5": False, "6": False})
    yield dev
    dev.close()


def test_polls_and_commands_share_one_connection(heater):
    d = devmod.BornholmDevice("127.0.0.40", "bfPERSIST", KEY, "3.3", "bornholm_smart_1kw")
    for _ in range(20):
        d.update()
    d.set_target_temperature(24)
    d.set_eco(True)
    d.set_preset("low")
    d.update()
    assert heater.connections == 1
    assert d.target_temperature == 24 and d.eco_on is True and d.preset == "low"
    assert heater.dps["2"] == 24 and heater.dps["5"] is True and heater.dps["4"] == "low"
    d.close()


def test_recovers_after_dropped_connection(heater):
    d = devmod.BornholmDevice("127.0.0.40", "bfPERSIST", KEY, "3.3", "bornholm_smart_1kw")
    d.update()
    before = heater.connections
    heater.drop_clients()
    time.sleep(0.1)
    for _ in range(3):  # tinytuya retries, or our next poll reconnects
        try:
            d.update()
            break
        except devmod.BornholmError:
            continue
    else:
        pytest.fail("did not reconnect")
    assert heater.connections == before + 1
    d.close()


def test_unsolicited_update_between_polls(heater):
    d = devmod.BornholmDevice("127.0.0.40", "bfPERSIST", KEY, "3.3", "bornholm_smart_1kw")
    d.update()
    heater.push({"2": 19})  # someone used the heater's own buttons
    time.sleep(0.1)
    d.update()
    d.update()
    assert d.target_temperature == 19
    assert d.is_on is True and d.current_temperature == 20  # nothing lost by merging
    d.close()
