"""Minimal fake Tuya v3.3 device (TCP 6668) for network-level tests."""

import json
import socket
import threading

from tinytuya.core import command_types as CT
from tinytuya.core import header as H
from tinytuya.core import message_helper as MH
from tinytuya.core.crypto_helper import AESCipher


class FakeTuyaDevice:
    def __init__(self, ip, dev_id, key, dps):
        self.dev_id, self.cipher, self.dps = dev_id, AESCipher(key.encode()), dps
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind((ip, 6668))
        self.srv.listen(8)
        threading.Thread(target=self._accept, daemon=True).start()

    def close(self):
        try:
            self.srv.shutdown(socket.SHUT_RDWR)  # wakes the blocked accept()
        except OSError:
            pass
        self.srv.close()

    def _accept(self):
        while True:
            try:
                conn, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _reply(self, conn, seq, cmd, payload, header):
        body = b""
        if payload is not None:
            body = self.cipher.encrypt(json.dumps(payload).encode(), use_base64=False)
            if header:
                body = H.PROTOCOL_33_HEADER + body
        body = b"\x00\x00\x00\x00" + body  # retcode
        msg = MH.TuyaMessage(seq, cmd, 0, body, 0, True, H.PREFIX_55AA_VALUE, False)
        conn.sendall(MH.pack_message(msg))

    def _handle(self, conn):
        with conn:
            buf = b""
            while True:
                try:
                    data = conn.recv(4096)
                except OSError:
                    return
                if not data:
                    return
                buf += data
                while len(buf) >= 16:
                    try:
                        m = MH.unpack_message(buf, no_retcode=True)
                    except Exception:
                        break
                    buf = buf[16 + int.from_bytes(buf[12:16], "big"):]
                    raw = m.payload[15:] if m.payload.startswith(b"3.3") else m.payload
                    try:
                        req = json.loads(self.cipher.decrypt(raw, use_base64=False))
                    except Exception:
                        return  # wrong key: drop the connection like a real device
                    if m.cmd == CT.DP_QUERY:
                        self._reply(conn, m.seqno, CT.DP_QUERY, {"devId": self.dev_id, "dps": self.dps}, False)
                    elif m.cmd == CT.CONTROL:
                        self.dps.update(req["dps"])
                        self._reply(conn, m.seqno, CT.CONTROL, None, False)
                        self._reply(conn, 0, CT.STATUS, {"devId": self.dev_id, "dps": req["dps"]}, True)
