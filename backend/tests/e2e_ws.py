"""E2e WS client đo DoD M5 — chạy ngoài pytest (không thu tên test_ nên không bị collect).

    # 1) snapshot + nhịp telemetry (so với WS_TELEMETRY_MIN_INTERVAL_MS của backend):
    python tests/e2e_ws.py rate --url ws://localhost:8000/ws --window 10 --interval-ms 250
    # 2) chờ frame status (kill simulator khi script đang chạy):
    python tests/e2e_ws.py wait --url ws://localhost:8000/ws --type status --state offline
    # 3) giữ kết nối + reconnect (test ping 30s / restart backend):
    python tests/e2e_ws.py hold --url ws://localhost:8000/ws --seconds 65

EXIT 0 = đạt, 1 = fail (in số đo ra stdout).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter

import websockets


async def _read_frame(ws, timeout: float) -> dict | None:
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout)
    except TimeoutError:
        return None
    return json.loads(raw)


async def _expect_snapshot(ws) -> float:
    t0 = time.monotonic()
    while True:
        frame = await _read_frame(ws, 5.0)
        if frame is None:
            raise RuntimeError("không nhận được snapshot trong 5 s")
        if frame.get("type") == "snapshot":
            return time.monotonic() - t0


async def cmd_rate(url: str, window: float, interval_ms: int, gateway: str | None) -> int:
    async with websockets.connect(url) as ws:
        snap_s = await _expect_snapshot(ws)
        print(f"snapshot nhận sau {snap_s * 1000:.0f} ms")
        kinds: Counter[str] = Counter()
        first = last = None
        t_start = time.monotonic()
        while time.monotonic() - t_start < window:
            frame = await _read_frame(ws, window)
            if frame is None:
                break
            kinds[frame["type"]] += 1
            if frame["type"] == "telemetry" and (
                not gateway or frame["data"]["gateway_id"] == gateway
            ):
                now = time.monotonic()
                first = now if first is None else first
                last = now
        n = kinds["telemetry"]
        span = (last - first) if n > 1 and first is not None else 0.0
        expected = window * 1000 / interval_ms
        period = 1000 * span / (n - 1) if n > 1 else float("nan")
        print(f"telemetry frames={n} kỳ_vọng≈{expected:.0f} (cửa sổ {window}s / {interval_ms}ms)")
        print(f"chu_kỳ_tb={period:.0f} ms kinds={dict(kinds)}")
        ok = abs(n - expected) <= expected * 0.10
        print("RATE", "PASS" if ok else "FAIL")
        return 0 if ok else 1


async def cmd_wait(url: str, wanted: str, state: str | None, timeout: float) -> int:
    async with websockets.connect(url) as ws:
        await _expect_snapshot(ws)
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            frame = await _read_frame(ws, timeout)
            if frame is None:
                break
            if frame.get("type") == wanted:
                dt = time.monotonic() - t0
                payload = json.dumps(frame["data"], ensure_ascii=False)[:120]
                print(f"frame {wanted} sau {dt:.1f} s: {payload}")
                if state and frame["data"].get("state") != state:
                    print("WAIT FAIL (state khác mong muốn)")
                    return 1
                print("WAIT", "PASS" if dt < 5.0 else "FAIL (>5s)")
                return 0 if dt < 5.0 else 1
        print(f"WAIT FAIL — không thấy frame {wanted} trong {timeout}s")
        return 1


async def cmd_hold(url: str, seconds: float) -> int:
    async with websockets.connect(url) as ws:
        await _expect_snapshot(ws)
        kinds: Counter[str] = Counter()
        t0 = time.monotonic()
        while time.monotonic() - t0 < seconds:
            frame = await _read_frame(ws, 2.0)
            if frame is not None:
                kinds[frame["type"]] += 1
        print(f"giữ kết nối {seconds:.0f}s (server ping 30s): {dict(kinds)}")
        return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["rate", "wait", "hold"])
    p.add_argument("--url", default="ws://localhost:8000/ws")
    p.add_argument("--window", type=float, default=10.0)
    p.add_argument("--interval-ms", type=int, default=250)
    p.add_argument("--gateway", default=None)
    p.add_argument("--type", default="status")
    p.add_argument("--state", default=None)
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--seconds", type=float, default=65.0)
    a = p.parse_args()
    if a.mode == "rate":
        return asyncio.run(cmd_rate(a.url, a.window, a.interval_ms, a.gateway))
    if a.mode == "wait":
        return asyncio.run(cmd_wait(a.url, a.type, a.state, a.timeout))
    return asyncio.run(cmd_hold(a.url, a.seconds))


if __name__ == "__main__":
    sys.exit(main())
