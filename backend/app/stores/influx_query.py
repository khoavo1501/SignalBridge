import asyncio
from datetime import datetime

from influxdb_client import InfluxDBClient

from app.config import get_settings

_client: InfluxDBClient | None = None


def _get_client() -> InfluxDBClient:
    global _client
    s = get_settings()
    if _client is None:
        _client = InfluxDBClient(url=s.influx_url, token=s.influx_token, org=s.influx_org)
    return _client


def _esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _flux_base(gateway_id, slave_addr, signals, start, stop) -> str:
    return "\n".join(
        [
            f'from(bucket: "{_esc(get_settings().influx_bucket)}")',
            f"|> range(start: {start.isoformat()}, stop: {stop.isoformat()})",
            f'|> filter(fn: (r) => r._measurement == "telemetry"'
            f' and r.gateway_id == "{_esc(gateway_id)}"'
            f' and r.slave_addr == "{int(slave_addr)}")',
            "|> filter(fn: (r) => "
            + " or ".join(f'r._field == "{_esc(s)}"' for s in signals)
            + ")",
            '|> group(columns: ["_field"])',
        ]
    )


def _history_fluxes(gateway_id, slave_addr, signals, start, stop, agg, limit) -> list[str]:
    """Danh sách flux phải chạy + merge kết quả. Signal bool (quy ước tiền tố di_) không
    mean trực tiếp được; InfluxDB 2.7 không có typeof() để làm trong một query."""
    n = int(limit)
    tail = f'\n|> sort(columns: ["_time"])\n|> limit(n: {n})'
    if not agg:
        return [_flux_base(gateway_id, slave_addr, signals, start, stop) + tail]
    numeric = [s for s in signals if not s.startswith("di_")]
    digital = [s for s in signals if s.startswith("di_")]
    out = []
    if numeric:
        out.append(
            _flux_base(gateway_id, slave_addr, numeric, start, stop)
            + f"\n|> aggregateWindow(every: {_esc(agg)}, fn: mean, createEmpty: false)"
            + tail
        )
    if digital:
        out.append(
            _flux_base(gateway_id, slave_addr, digital, start, stop)
            + "\n|> map(fn: (r) => ({ r with _value: if r._value then 1.0 else 0.0 }))"
            + f"\n|> aggregateWindow(every: {_esc(agg)}, fn: mean, createEmpty: false)"
            + tail
        )
    return out


def _run_sync(flux: str):
    s = get_settings()
    tables = _get_client().query_api().query(query=flux, org=s.influx_org)
    out: dict[str, list[tuple[datetime, object]]] = {}
    for table in tables:
        for rec in table.records:
            field = rec.get_field()
            value = rec.get_value()
            out.setdefault(field, []).append((rec.get_time(), value))
    return out


async def query_history(gateway_id, slave_addr, signals, start, stop, agg=None, limit=5000):
    result: dict[str, list[tuple[datetime, object]]] = {}
    for flux in _history_fluxes(gateway_id, slave_addr, signals, start, stop, agg, limit):
        part = await asyncio.to_thread(_run_sync, flux)
        for field, points in part.items():
            result.setdefault(field, []).extend(points)
    for points in result.values():
        points.sort(key=lambda p: p[0])
    return result


async def query_diag_latest(gateway_id: str) -> dict | None:
    flux = (
        f'from(bucket: "{_esc(get_settings().influx_bucket)}")'
        "|> range(start: -7d)"
        f'|> filter(fn: (r) => r._measurement == "diag" and r.gateway_id == "{_esc(gateway_id)}")'
        '|> group(columns: ["_field"])'
        "|> last()"
    )
    rows = await asyncio.to_thread(_run_sync, flux)
    if not rows:
        return None
    fields: dict[str, object] = {}
    ts: datetime | None = None
    slave_stats: dict[int, dict[str, int]] = {}
    for field, points in rows.items():
        t, value = points[0]
        ts = max(ts, t) if ts else t
        if field.startswith("slave_"):
            _, addr, stat = field.split("_", 2)
            slave_stats.setdefault(int(addr), {"addr": int(addr)})[stat] = value
        else:
            fields[field] = value
    return {
        "received_at": ts,
        "fields": fields,
        "slave_stats": sorted(slave_stats.values(), key=lambda s: s["addr"]),
    }
