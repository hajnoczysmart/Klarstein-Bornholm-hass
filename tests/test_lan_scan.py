"""LAN rediscovery: decode real Tuya-style UDP broadcasts."""

import json
import socket
import threading
import time

from tinytuya.core.udp_helper import encrypt, udpkey

from klarstein_bornholm import device as devmod


def _broadcast(port, payload, encrypted=True, count=5):
    data = json.dumps(payload).encode()
    if encrypted:
        data = encrypt(data, udpkey)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        for _ in range(count):
            s.sendto(data, ("127.0.0.1", port))
            time.sleep(0.2)


def _reset_cache():
    devmod._SCAN_CACHE.update(time=0.0, found={})


def test_scan_finds_heater_and_stops_early():
    _reset_cache()
    other = {"ip": "192.168.1.134", "gwId": "bfOTHER", "version": "3.4", "productKey": "x"}
    mine = {"ip": "192.168.1.240", "gwId": "bfMINE", "version": "3.4", "productKey": "dcxerfhhzu2x1bei"}
    t = threading.Thread(target=lambda: (_broadcast(6667, other, count=2), _broadcast(6667, mine)))
    start = time.monotonic()
    t.start()
    found = devmod.find_on_lan("bfMINE", timeout=8)
    t.join()
    assert found == {"ip": "192.168.1.240", "version": "3.4"}
    assert time.monotonic() - start < 6  # stopped as soon as it was seen
    # the other heater is cached for a concurrent lookup
    assert devmod.find_on_lan("bfOTHER", timeout=0.1)["ip"] == "192.168.1.134"


def test_scan_plain_v31_and_garbage():
    _reset_cache()
    payload = {"ip": "10.0.0.5", "gwId": "bfOLD", "version": "3.1"}
    t = threading.Thread(target=lambda: (_broadcast(6666, {"junk": 1}, count=1),
                                         _broadcast(6666, payload, encrypted=False)))
    t.start()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.sendto(b"\x00garbage\xff", ("127.0.0.1", 6666))
    found = devmod.find_on_lan("bfOLD", timeout=8)
    t.join()
    assert found == {"ip": "10.0.0.5", "version": "3.1"}


def test_scan_timeout_returns_empty():
    _reset_cache()
    assert devmod.find_on_lan("bfNOBODY", timeout=0.5) == {}
