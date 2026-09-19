"""Gateway simulator — phát lại hành vi GW_S7200_01 theo docs/payloads/.

Mô phỏng đúng firmware 1.1.0:
- topic devices/<GATEWAY_ID>/<category>, payload có ts=0 (NTP tắt)
- telemetry QoS0 mỗi 100ms: 8 DI + ai_raw + hr_50; CHỈ --with-hr54 mới có hr_54/hr_58
  (region 54-58 hiện chưa được poll thật — rủi ro #6 của báo cáo)
- status online QoS1 retain mỗi 30s + LWT offline (willDelay 0, keepalive ngắn để test)
- info QoS1 retain khi connect; diag QoS0; event SLAVE_COMM_LOST rate-limit 30s khi --fail-rate

Env: SIM_MQTT_HOST, SIM_MQTT_PORT, SIM_GATEWAY_ID, SIM_INTERVAL_MS
Chạy: python simulator.py [--duration 60] [--with-hr54] [--fail-rate 0.1] [--keepalive 2]
"""

import argparse
import json
import os
import random
import signal
import threading
import time

import paho.mqtt.client as mqtt

CATEGORY_TELEMETRY = "telemetry"


class Simulator:
    def __init__(self, host: str, port: int, gid: str, interval_ms: int, with_hr54: bool,
                 fail_rate: float, keepalive: int, diag_interval_s: float):
        self.gid = gid
        self.interval = interval_ms / 1000.0
        self.with_hr54 = with_hr54
        self.fail_rate = fail_rate
        self.diag_interval_s = diag_interval_s
        self.seq = 0
        self.stop = threading.Event()
        self.last_event_s = 0.0
        self.connected = threading.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sim-{gid}")
        lwt = {"device_id": gid, "ts": 0, "type": "status", "state": "offline",
               "reason": "unexpected_disconnect"}
        self.client.will_set(f"devices/{gid}/status", json.dumps(lwt), qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.connect(host, port, keepalive=keepalive)

    def _on_connect(self, client, _userdata, _flags, _rc, _props=None):
        self.publish_info()
        self.publish_status("online")
        self.connected.set()

    def _pub(self, category: str, payload: dict, qos: int, retain: bool = False):
        self.client.publish(f"devices/{self.gid}/{category}", json.dumps(payload), qos=qos, retain=retain)

    def publish_info(self):
        info = {"device_id": self.gid, "ts": 0, "type": "info", "master": {
            "fw_version": "1.1.0", "hw_version": "STM32F411_W5500_RS485",
            "ip": "192.168.1.50", "mac": "02:53:37:20:00:01", "reset_reason": "POWER_ON",
            "slaves": [{"id": 1, "addr": 1, "name": "S7-200"}]}}
        self._pub("info", info, qos=1, retain=True)

    def publish_status(self, state: str):
        st = {"device_id": self.gid, "ts": 0, "type": "status", "state": state,
              "uptime_s": int(time.monotonic() - self.t0)}
        self._pub("status", st, qos=1, retain=True)

    def publish_telemetry(self):
        di = [random.random() < 0.5 for _ in range(8)]
        di_word = sum(b << i for i, b in enumerate(di))
        ai = random.randint(0, 27648)
        regs = {f"di_{i}": di[i] for i in range(8)}
        regs["hr_50"] = ai
        if self.with_hr54:
            regs["hr_54"] = self.seq * 1000
            regs["hr_58"] = self.seq % 65536
        t = {"device_id": self.gid, "ts": 0, "type": "telemetry", "seq": self.seq,
             "fw": "1.1.0",
             "plc": {"di_word": di_word, "di": di + [False] * 8, "ai": ai},
             "registers": regs}
        self._pub(CATEGORY_TELEMETRY, t, qos=0)
        self.seq += 1

    def publish_fail_event(self):
        now = time.monotonic()
        if now - self.last_event_s < 30:
            return
        self.last_event_s = now
        ev = {"device_id": self.gid, "ts": 0, "type": "event", "events": [{
            "code": "SLAVE_COMM_LOST", "severity": "critical",
            "message": "Modbus RTU read failed", "source": "slave:1"}]}
        self._pub("event", ev, qos=1)

    def publish_diag(self):
        d = {"device_id": self.gid, "ts": 0, "type": "diag", "stats": {
            "poll_cycle_ms": int(self.interval * 1000), "uptime_s": int(time.monotonic() - self.t0),
            "slaves": [{"id": 1, "addr": 1, "ok": self.seq, "fail": 0}],
            "tx_packets": self.seq, "tx_failures": 0, "mqtt_reconnect": 1}}
        self._pub("diag", d, qos=0)

    def run(self, duration_s: float | None):
        self.t0 = time.monotonic()
        threading.Thread(target=self.client.loop_start, daemon=True).start()
        if not self.connected.wait(10):
            raise SystemExit("simulator: MQTT connect timeout")
        last_status = last_diag = time.monotonic()
        deadline = None if duration_s is None else time.monotonic() + duration_s
        while not self.stop.is_set() and (deadline is None or time.monotonic() < deadline):
            cycle_start = time.monotonic()
            if self.fail_rate and random.random() < self.fail_rate:
                self.publish_fail_event()
            else:
                self.publish_telemetry()
            now = time.monotonic()
            if now - last_status >= 30:
                self.publish_status("online")
                last_status = now
            if now - last_diag >= self.diag_interval_s:
                self.publish_diag()
                last_diag = now
            time.sleep(max(0.0, self.interval - (time.monotonic() - cycle_start)))
        # graceful stop: ngắt loop — LWT KHÔNG bay (broker chỉ gửi will khi mất kết nối đột ngột,
        # đúng hành vi firmware — rủi ro #7 báo cáo). Test LWT bằng kill -9.
        self.client.disconnect()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default=os.environ.get("SIM_MQTT_HOST", "localhost"))
    p.add_argument("--port", type=int, default=int(os.environ.get("SIM_MQTT_PORT", "1883")))
    p.add_argument("--gateway-id", default=os.environ.get("SIM_GATEWAY_ID", "GW_S7200_01"))
    p.add_argument("--interval-ms", type=int, default=int(os.environ.get("SIM_INTERVAL_MS", "100")))
    p.add_argument("--duration", type=float, default=None)
    p.add_argument("--with-hr54", action="store_true")
    p.add_argument("--fail-rate", type=float, default=0.0)
    p.add_argument("--keepalive", type=int, default=2)
    p.add_argument("--diag-interval-s", type=float, default=600)
    args = p.parse_args()

    sim = Simulator(args.host, args.port, args.gateway_id, args.interval_ms, args.with_hr54,
                    args.fail_rate, args.keepalive, args.diag_interval_s)
    signal.signal(signal.SIGTERM, lambda *_: sim.stop.set())
    signal.signal(signal.SIGINT, lambda *_: sim.stop.set())
    print(f"simulator {args.gateway_id} → {args.host}:{args.port} interval={args.interval_ms}ms "
          f"hr54={args.with_hr54} fail_rate={args.fail_rate}")
    sim.run(args.duration)
    print(f"done, sent {sim.seq} telemetry")


if __name__ == "__main__":
    main()
