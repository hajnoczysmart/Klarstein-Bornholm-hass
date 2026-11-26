"""Unicast subnet sweep: find a heater whose IP changed, across subnets."""

import time

import pytest

from fake_tuya import FakeTuyaDevice
from klarstein_bornholm import device as devmod


@pytest.fixture(scope="module")
def lan():
    # "living room" heater moved to .23; the "corridor" heater now holds its old IP .10
    other = FakeTuyaDevice("127.0.0.10", "bfCORRIDOR", "0123456789abcdef", {"1": True})
    mine = FakeTuyaDevice("127.0.0.23", "bfLIVING", "fedcba9876543210", {"1": False, "2": 21})
    yield
    other.close()
    mine.close()


def test_sweep_finds_moved_heater(lan):
    # old address answers, but with the wrong key (Tuya error 914)
    with pytest.raises(devmod.BornholmError):
        devmod.probe("127.0.0.10", "bfLIVING", "fedcba9876543210", "3.3")
    start = time.monotonic()
    found = devmod.sweep_subnet("127.0.0.10", "bfLIVING", "fedcba9876543210", "3.3")
    assert found == {"ip": "127.0.0.23", "version": "3.3"}
    assert time.monotonic() - start < 30
    # and the other heater is found with its own key
    assert devmod.sweep_subnet("127.0.0.23", "bfCORRIDOR", "0123456789abcdef", "3.3")["ip"] == "127.0.0.10"


def test_sweep_not_found(lan):
    assert devmod.sweep_subnet("127.0.0.10", "bfGONE", "aaaaaaaaaaaaaaaa", "3.3") == {}
    assert devmod.sweep_subnet("not-an-ip", "x", "k", "3.3") == {}
