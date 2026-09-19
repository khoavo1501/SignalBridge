# PROJECT_PLAN.md — Hệ thống giám sát PLC realtime (SignalBridge)

- **Phiên bản:** 1.3 (2026-09-19 — v1.1 chốt Q1/Q2; v1.2 khởi tạo hệ thống docs + AGENTS.md; v1.3 chốt Q3–Q6, Q8 → retention 60 ngày, thêm M8 Admin UI + gateway CRUD; Q7 + công thức scale Q2 cuối cùng còn mở)
- **Phạm vi:** Phase 1 — vài gateway, vài chục thiết bị PLC. Không làm cảnh báo chủ động (email/SMS) ở phase này.
- **Ground truth payload:** `docs/payloads/BAO_CAO_PAYLOAD_Gateway_S7200.md` — mọi thiết kế bên dưới bám sát file này, không tự suy diễn thêm tín hiệu.
- **Stack đã chốt (không đổi):** FastAPI (Python) · React + TypeScript + Vite + Recharts + lucide-react · PostgreSQL · InfluxDB · EMQX · Redis · Nginx · Docker Compose · Git.

---

## 1. Kiến trúc tổng thể

### 1.1 Luồng dữ liệu

```
 PLC (S7-200, Modbus RTU/RS485)
   │  poll mỗi 100 ms
   ▼
 Gateway GW_S7200_01 (STM32F411 + W5500)
   │  MQTT (không TLS) — topic devices/<gateway_id>/<category>
   │  categories: telemetry | status (LWT, retain) | info (retain) | diag | event
   ▼
 EMQX (broker)
   │  subscribe: devices/+/+
   ▼
 ┌────────────────────────────────────────────────────────────┐
 │ Backend FastAPI — MỘT service Python duy nhất              │
 │                                                            │
 │  [MQTT Listener] → [Parser Registry / adapter theo gateway]│
 │        │                │                                  │
 │        │                ▼                                  │
 │        │        NormalizedMessage (format nội bộ)          │
 │        │                │                                  │
 │        │      ┌─────────┼──────────────┐                   │
 │        │      ▼         ▼              ▼                   │
 │        │  InfluxDB   PostgreSQL      Redis                 │
 │        │  (telemetry (gateways,    (latest values,         │
 │        │   time-series, slaves,      online +              │
 │        │   diag)     events,        freshness ts)          │
 │        │              meta)             │                  │
 │        │                                ▼                  │
 │        │                     [REST API]  [WebSocket hub]   │
 └────────┼──────────────────────────────────┼────────────────┘
          │ (last will / status được listener cập nhật trực tiếp)
          ▼
 Frontend React (dashboard)  ◄── Nginx (reverse proxy /api, /ws → backend)
```

### 1.2 Vì sao dùng 1 service Python duy nhất (modular monolith)

- Ở quy mô vài gateway × poll 100 ms, tổng tải ~vài chục msg/giây — quá nhỏ để tách microservices; tách sớm chỉ tăng độ phức tạp vận hành (IPC, deployment, tracing) mà không lợi ích.
- MQTT listener chạy nền trong cùng tiến trình (asyncio task cùng event loop với FastAPI), thay vì service riêng → không cần hàng đợi trung gian.
- **Quan trọng:** cấu trúc code tách module rõ ràng (`ingestion/`, `parsers/`, `stores/`, `api/`, `ws/`) để mỗi module sau này nâng lên service độc lập mà không đổi logic bên trong.

**Điều kiện cần tách service (trigger points — đo được, không đoán):**

| Khi nào | Tách cái gì thành |
|---|---|
| > ~50 gateway hoặc ingestion khiến API p95 > 200 ms / event loop bị block thường xuyên | Tách `ingestion` (MQTT listener + parser + ghi DB) thành worker độc lập |
| History query lớn làm chậm realtime | Tách `query service` (đọc InfluxDB) riêng |
| Nhiều instance WS cần đồng bộ broadcast | Đưa fan-out WS qua Redis Pub/Sub (đã thiết kế sẵn fallback này, xem §4.4) |

### 1.3 Xử lý broker hiện tại — **đã chốt (2026-09-19)**

Gateway hiện trỏ tới **Mosquitto 192.168.1.4:1883** (theo báo cáo). **Quyết định: deploy EMQX trên máy chủ mới + đổi firmware sang IP broker mới** (không thay Mosquitto tại chỗ).

- EMQX là service trong docker-compose (§5.2); host/IP của máy chủ compose cần công bố cho team firmware để cập nhật cấu hình broker trên từng gateway.
- Firmware đổi IP nhưng **giữ nguyên topic/payload/schema** → backend không đổi logic, chỉ là giá trị env `MQTT_HOST`.
- **Stage chuyển tiếp:** gateway nào chưa đổi firmware vẫn publish về Mosquitto cũ → dashboard chưa thấy được. Cho đến khi firmware update xong, dev/test dùng `gateway_simulator` trỏ thẳng vào EMQX (M2). Nếu cần smoke-test với gateway thật trước khi đổi firmware, có thể tạm trỏ `MQTT_HOST` của backend về Mosquitto cũ (chỉ đổi env, không đổi code).

---

## 2. Thiết kế parser theo adapter pattern

### 2.1 Nguyên tắc

- **Không hard-code schema của GW_S7200_01 vào pipeline.** Mỗi loại gateway/firmware có 1 parser adapter; tất cả map về **cùng một format nội bộ thống nhất** (NormalizedMessage). Toàn bộ phần còn lại (stores, API, WS, frontend) chỉ biết format nội bộ, không bao giờ thấy payload thô.
- Định tuyến adapter theo `gateway_id`: bảng `gateways.adapter_key` trong Postgres quyết định dùng parser nào cho từng gateway (một loại gateway có nhiều thiết bị thì dùng chung 1 adapter).
- Parser **không raise exception** vì thiếu field: dùng `.get()` với default, field vắng mặt đơn giản là không có trong output (ràng buộc #3 của đề bài). Payload không parse được JSON / sai `type` → log cảnh báo + đếm vào metric `parse_errors`, không làm chết listener.

### 2.2 Format nội bộ thống nhất (pydantic models, `app/parsers/base.py`)

```python
class NormalizedMessage(BaseModel):
    kind: Literal["telemetry", "status", "info", "diag", "event"]
    gateway_id: str
    received_at: datetime        # server-side, BẮT BUỘC dùng thay ts (ràng buộc #1)
    adapter_key: str             # vd "s7200_v1" — để trace nguồn

class Telemetry(NormalizedMessage):
    slave_addr: int              # Modbus slave ID; GW hiện tại luôn = 1, mặc định từ info/registry
    seq: int | None
    signals: dict[str, SignalValue]   # TÊN CHUẨN HÓA, xem 2.3
    raw: dict                     # payload gốc, lưu để debug (jsonb/log, không vào Influx)

class Status(NormalizedMessage):
    state: Literal["online", "offline"]
    uptime_s: int | None
    reason: str | None            # vd "unexpected_disconnect" từ LWT

class GatewayInfo(NormalizedMessage):
    fw_version: str | None
    hw_version: str | None
    ip: str | None
    mac: str | None
    reset_reason: str | None
    slaves: list[SlaveRef]        # SlaveRef(addr:int, name:str|None) — hỗ trợ n slave (ràng buộc #4)

class Diag(NormalizedMessage):
    poll_cycle_ms: int | None
    uptime_s: int | None
    slave_stats: list[SlaveStat]  # SlaveStat(addr, ok:int, fail:int)
    tx_packets: int | None        # lưu ý: semantics chưa đúng (báo cáo mục 2) — chỉ display thô
    tx_failures: int | None
    mqtt_reconnect: int | None

class GatewayEvent(NormalizedMessage):
    events: list[EventItem]       # EventItem(code, severity, message, source, slave_addr|None)
```

### 2.3 Quy ước tên signal chuẩn (canonical)

Parser map field thô → tên chuẩn. Signal nào cũng là `{"value": ...}` kèm metadata optional. Với GW_S7200:

| Nguồn thô | Tên chuẩn | Ghi chú |
|---|---|---|
| `plc.di[0..7]` | `di_0` … `di_7` (bool) | **Chỉ 8 bit đầu hợp lệ** — bit 8–15 luôn false (báo cáo rủi ro #5), parser cố ý bỏ qua |
| `plc.di_word` | `di_word` (int) | |
| `plc.ai` / `registers.hr_50` | `ai_raw` (int) | Hai nguồn trùng giá trị → chỉ giữ một signal `ai_raw`; **raw, chưa scale** |
| `registers.hr_54` | `hc0` (int, counter 32-bit) | Vắng mặt nếu region chưa poll offset 54–55 → **không có key, không raise** (ràng buộc #3 + rủi ro #6) |
| `registers.hr_58` | `c0` (int) | Tương tự |
| `registers.*` còn lại (động) | `reg_<ten>` (int/bool) | Field lạ không nằm trong bảng map → đưa vào `signals` với tên `reg_<ten>` nguyên bản để không mất dữ liệu |

Mapping thô → chuẩn nằm trong 1 dict常量 của adapter (`FIELD_MAP`), dễ sửa khi firmware đổi.

### 2.4 Interface parser & registry

```python
class GatewayAdapter(ABC):
    key: str  # "s7200_v1"

    @abstractmethod
    def match(self, gateway_id: str, topic: str, payload: dict) -> bool: ...

    @abstractmethod
    def parse(self, gateway_id: str, topic: str, payload: dict,
              received_at: datetime) -> list[NormalizedMessage]: ...
```

- `parse` trả **list** vì 1 message thô có thể chứa nhiều logic (vd event nhiều phần tử → nhiều bản ghi, hoặc tương lai 1 payload gộp nhiều slave).
- **Registry** (`app/parsers/registry.py`): dict `adapter_key -> instance`. Thứ tự chọn adapter: `gateways.adapter_key` trong DB → nếu gateway chưa đăng ký thì thử `match()` của từng adapter (fallback, vd theo pattern `GW_S7200_*`).
- **Thêm gateway loại mới** = thêm 1 file `app/parsers/<loai>.py` kế thừa `GatewayAdapter`, khai báo `ADAPTERS = [S7200Adapter(), NewTypeAdapter()]` trong registry, và set `adapter_key` cho gateway đó trong DB. Không sửa pipeline.
- Unit test bắt buộc cho adapter: test payload đúng theo báo cáo; test payload thiếu `hr_54`/`hr_58`; test payload thiếu hẳn `plc`; test JSON rác.

### 2.5 Adapter `s7200_v1` — ánh xạ theo đúng báo cáo

- Topic `devices/+/telemetry` → `Telemetry(slave_addr=1, seq, signals từ plc+registers)`.
- Topic `.../status` → `Status`; nhận cả LWT retain `state:"offline", reason:"unexpected_disconnect"`.
- Topic `.../info` → `GatewayInfo` (dùng để upsert `gateways` + `slaves` trong Postgres — nguồn duy nhất khai báo n slave).
- Topic `.../diag` → `Diag`.
- Topic `.../event` → `GatewayEvent`; `source: "slave:1"` → parse `slave_addr=1`.
- Bỏ qua `ts` trong payload hoàn toàn (ràng buộc #1) — chỉ ghi `received_at`.

---

## 3. Schema cơ sở dữ liệu

### 3.1 PostgreSQL (quan hệ cấu hình + sự kiện)

```sql
-- gateways: 1 dòng / gateway vật lý
CREATE TABLE gateways (
    id            BIGSERIAL PRIMARY KEY,
    gateway_id    TEXT NOT NULL UNIQUE,          -- "GW_S7200_01" (từ payload)
    display_name  TEXT NOT NULL,
    adapter_key   TEXT NOT NULL DEFAULT 's7200_v1',
    fw_version    TEXT,                          -- nullable: chưa nhận info lần nào
    hw_version    TEXT,
    ip            TEXT,
    mac           TEXT,
    enabled       BOOLEAN NOT NULL DEFAULT TRUE, -- gateway "tạm ngưng giám sát"
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- slaves: quan hệ 1-nhiều gateways.slaves (hỗ trợ n slave, ràng buộc #4)
CREATE TABLE slaves (
    id            BIGSERIAL PRIMARY KEY,
    gateway_id    BIGINT NOT NULL REFERENCES gateways(id) ON DELETE CASCADE,
    slave_addr    INTEGER NOT NULL,              -- Modbus slave ID
    name          TEXT,                          -- "S7-200", nullable
    protocol      TEXT,                          -- "modbus-rtu", nullable (gateway loại khác)
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (gateway_id, slave_addr)
);

-- định nghĩa/khai báo signal chuẩn + cấu hình scale (ràng buộc #2)
CREATE TABLE signal_defs (
    id            BIGSERIAL PRIMARY KEY,
    gateway_id    BIGINT NOT NULL REFERENCES gateways(id) ON DELETE CASCADE,
    key           TEXT NOT NULL,                 -- "ai_raw"
    display_name  TEXT NOT NULL,                 -- "Tốc độ động cơ"
    unit          TEXT,                          -- "RPM" — chỉ hiển thị khi đã xác nhận scale
    scale         JSONB,                         -- {"a": null, "b": null, "formula": null} — CHỜ team hardware (Q2)
    kind          TEXT NOT NULL CHECK (kind IN ('analog','digital','counter')),
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (gateway_id, key)
);

-- gateway_events: event + các mốc status đáng lưu (online/offline)
CREATE TABLE gateway_events (
    id            BIGSERIAL PRIMARY KEY,
    gateway_id    BIGINT NOT NULL REFERENCES gateways(id) ON DELETE CASCADE,
    slave_addr    INTEGER,                       -- nullable: event cấp gateway
    code          TEXT NOT NULL,                 -- "SLAVE_COMM_LOST" | "STATUS_ONLINE" | "STATUS_OFFLINE"
    severity      TEXT NOT NULL DEFAULT 'info',  -- info | warning | critical
    message       TEXT,
    source        TEXT,                          -- nguyên văn field source
    received_at   TIMESTAMPTZ NOT NULL,          -- server time
    raw           JSONB                          -- payload gốc
);
CREATE INDEX idx_events_gw_time ON gateway_events (gateway_id, received_at DESC);
CREATE INDEX idx_events_code    ON gateway_events (code, received_at DESC);

CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,                 -- phase 1: tồn tại bảng + 1 user admin seed, API chưa enforce auth
    role          TEXT NOT NULL DEFAULT 'viewer',-- viewer | operator | admin (chỗ gắn auth sau, §4.5)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Ghi chú:
- `gw_status` **không** là cột trên `gateways` — trạng thái online/offline/tươi được tính từ Redis tại thời điểm API trả lời (xem 3.3), tránh ghi DB liên tục mỗi 100 ms và tránh trạng thái stale trong Postgres.
- Bảng `gateways`/`slaves` được **tự upsert từ payload `info`**, nhưng `display_name`, `adapter_key`, `enabled` do admin seed/quản lý → không xóa khi gateway mất kết nối.

### 3.2 InfluxDB (time-series telemetry + diag)

- **Bucket:** `plc` (InfluxDB 2.x), retention **60 ngày** (chốt Q5: 2026-09-19). Token auth qua env.
- **Measurement `telemetry`** — **mỗi slave một dòng dữ liệu riêng**, tag `slave_addr` phân tách, không gộp cứng theo gateway:
  - Tags: `gateway_id`, `slave_addr`, `adapter_key`
  - Fields: đúng tên signal chuẩn trong §2.3 (`di_0..di_7` bool, `di_word` int, `ai_raw` int, `hc0`/`c0` int, `reg_*`) — **chỉ ghi các field có mặt**, field vắng thì dòng đó không có field (thiết kế Influx chịu được sparse field → xử lý ràng buộc #3 tự nhiên).
  - Timestamp: `received_at` (server time), **không dùng `ts` payload**.
  - Ghi theo lô (batch ~1 s hoặc 500 điểm) để giảm round-trip; poll 100 ms × vài chục device vẫn rất nhỏ.
- **Measurement `diag`**: tags `gateway_id`; fields `uptime_s`, `tx_packets`, `tx_failures`, `mqtt_reconnect`, và per-slave `ok`/`fail` dạng field `slave_<addr>_ok`, `slave_<addr>_fail` (map trực tiếp từ `stats.slaves[]`).

### 3.3 Redis (cache trạng thái mới nhất — nguồn đọc của dashboard)

Key pattern (prefix `sb:`), tất cả giá trị JSON hoặc hash:

| Key | Nội dung | TTL |
|---|---|---|
| `sb:latest:{gateway_id}:{slave_addr}` | Hash: từng signal chuẩn + `_received_at` (ISO) + `_seq` | không TTL (luôn bị record mới đè) |
| `sb:status:{gateway_id}` | Hash: `state` (online/offline), `since`, `reason` | không TTL |
| `sb:last_seen:{gateway_id}` | String epoch giây — thời điểm nhận telemetry cuối (từ listener) | không TTL |

**Logic badge 3 trạng thái (ràng buộc #5) — tính ở API layer, không lưu sẵn:**

```
state_online = sb:status[gw].state == "online"      # từ topic status/LWT
fresh        = now - sb:last_seen[gw] < STALE_THRESHOLD_S   # từ topic telemetry
badge = online  nếu state_online && fresh
      = stale   nếu state_online && !fresh   ("online nhưng dữ liệu trễ")
      = offline nếu !state_online
```

`STALE_THRESHOLD_S` mặc định **10 s** (telemetry bình thường mỗi 100 ms; 10 s = mất ~100 gói liên tiếp, đủ xa để không báo giả khi mạng抖动), cấu hình qua env. Ghi chú thêm từ báo cáo rủi ro #8: telemetry QoS 0 có thể mất gói đơn lẻ — `seq` được lưu theo dõi để hiển thị "mất mát ước tính" ở trang chi tiết (tính gap `seq` trung bình trong cửa sổ diag, chỉ số tham khảo, không alert).

---

## 4. API & WebSocket contract

Base URL qua Nginx: `/api/v1`. Mọi response JSON; lỗi theo `{"error": {"code": "...", "message": "..."}}` + HTTP status. Timestamp mọi nơi là ISO-8601 UTC.

### 4.1 REST endpoints

| Method | Path | Mô tả |
|---|---|---|
| GET | `/api/v1/health` | health + kết nối DB/broker |
| GET | `/api/v1/dashboard/summary` | danh sách gateway + badge + chỉ số chính |
| GET | `/api/v1/gateways` | danh sách gateway chi tiết |
| POST | `/api/v1/gateways` | đăng ký gateway mới (Q8 — phục vụ UI admin M8) |
| PATCH | `/api/v1/gateways/{gateway_id}` | sửa `display_name`, `adapter_key`, `enabled` |
| DELETE | `/api/v1/gateways/{gateway_id}` | gỡ gateway khỏi giám sát (xóa cascade; dữ liệu Influx/Redis giữ nguyên, key Redis dọn theo) |
| GET | `/api/v1/gateways/{gateway_id}` | 1 gateway + slaves + meta (info) |
| GET | `/api/v1/gateways/{gateway_id}/latest` | giá trị mới nhất từng slave (Redis) |
| GET | `/api/v1/gateways/{gateway_id}/history` | chuỗi thời gian (InfluxDB) |
| GET | `/api/v1/gateways/{gateway_id}/events` | event list (Postgres, phân trang) |
| GET | `/api/v1/gateways/{gateway_id}/diag` | diag gần nhất + thống kê |

**Ví dụ — `GET /api/v1/dashboard/summary`:**

```json
{
  "generated_at": "2026-09-19T08:00:00Z",
  "stale_threshold_s": 10,
  "gateways": [
    {
      "gateway_id": "GW_S7200_01",
      "display_name": "Xưởng cơ khí 1",
      "badge": "online",
      "state": "online",
      "fresh": true,
      "last_telemetry_at": "2026-09-19T08:00:00.4Z",
      "fw_version": "1.1.0",
      "slave_count": 1,
      "primary_metrics": [
        { "key": "ai_raw", "display_name": "Tốc độ động cơ", "unit": null, "raw": 12345, "value": null, "scaled": false }
      ]
    }
  ]
}
```

> `value`/`scaled`: khi chưa có công thức scale (Q2), API trả `value = raw`, `scaled = false`, `unit = null` — frontend hiển thị kèm chú thích "(raw)". **Không đoán hệ số.**

**Ví dụ — `GET /api/v1/gateways/GW_S7200_01/history?slave=1&signals=ai_raw,hc0&from=2026-09-19T07:00:00Z&to=2026-09-19T08:00:00Z&agg=10s&limit=1000`:**

```json
{
  "gateway_id": "GW_S7200_01",
  "slave_addr": 1,
  "series": [
    { "signal": "ai_raw", "unit": null, "points": [ { "t": "2026-09-19T07:00:00Z", "v": 12345 }, { "t": "2026-09-19T07:00:10Z", "v": 12350 } ] }
  ],
  "count": 2
}
```

(`agg` optional: `raw|<duration>` theo Flux `aggregateWindow`; mặc định raw + `limit` 5000.)

**Ví dụ — `GET /api/v1/gateways/GW_S7200_01/events?limit=20&before=<iso>`:**

```json
{
  "events": [
    { "received_at": "2026-09-19T07:55:01Z", "code": "SLAVE_COMM_LOST", "severity": "critical",
      "message": "Modbus RTU read failed", "source": "slave:1", "slave_addr": 1 }
  ],
  "next_before": "2026-09-19T07:55:01Z"
}
```

**Contract đăng ký/cập nhật gateway (Q8 — UI admin, M8):**

```jsonc
// POST /api/v1/gateways
{ "gateway_id": "GW_S7200_02", "display_name": "Xưởng cơ khí 2", "adapter_key": "s7200_v1", "enabled": true }
// → 201: entity đầy đủ (slaves rỗng cho tới khi nhận info). 409 nếu gateway_id trùng.
// PATCH /api/v1/gateways/{gateway_id}  → chỉ chấp nhận display_name | adapter_key | enabled → 200
// validate: gateway_id khớp [A-Z0-9_]{1,64}; adapter_key phải tồn tại trong registry (422 nếu sai)
```

### 4.2 WebSocket

- Endpoint: `GET /ws` (upgrade, qua Nginx với `proxy_read_timeout` dài). Client gửi `{ "type": "subscribe", "gateways": ["GW_S7200_01"] }` (thiếu `gateways` = subscribe tất cả).
- Server gửi envelope: `{ "type": <kind>, "ts": <server_time_iso>, "data": {...} }` với `data` = NormalizedMessage đã serialize.

```json
{ "type": "telemetry", "ts": "...", "data": { "gateway_id": "GW_S7200_01", "slave_addr": 1, "seq": 43, "signals": { "ai_raw": 12346, "di_0": true }, "received_at": "..." } }
{ "type": "status",    "ts": "...", "data": { "gateway_id": "GW_S7200_01", "state": "offline", "reason": "unexpected_disconnect" } }
{ "type": "event",     "ts": "...", "data": { "gateway_id": "GW_S7200_01", "events": [ { "code": "SLAVE_COMM_LOST", "severity": "critical", "source": "slave:1", "message": "Modbus RTU read failed" } ] } }
```

- Khi client mới connect → server gửi ngay 1 frame `{ "type": "snapshot", ... }` chứa summary như §4.1 để khỏi chờ WS event.
- **Rate limiting mặc định:** telemetry 100 ms/payload/gateway → WS forward trực tiếp là chịu được ở quy mô hiện tại; nếu dashboard chỉ cần 1 Hz, backend aggregate theo env `WS_TELEMETRY_MIN_INTERVAL_MS` (mặc định 250 ms — throttle mỗi gateway/slave/signal-group). `status`/`event`/`info` luôn gửi ngay.
- Heartbeat: server ping 30 s; client reconnect với exponential backoff (logic phía frontend).
- Fan-out qua in-process hub; interface `Broadcaster` có 2 implementation: `LocalBroadcaster` (mặc định) và `RedisPubSubBroadcaster` (bật bằng env khi scale nhiều instance — xem §1.2).

### 4.3 `info` & `diag` qua WS

`info` gửi ngay khi có (upsert xong DB thì phát frame để frontend cập nhật slave list). `diag` gửi mỗi lần nhận (10 phút/lần — quá ít để hiển thị realtime, chủ nhiên dùng cho bảng thống kê).

### 4.4 Response header/behavior chung

- History query quá `to - from > 7 ngày` → 400 kèm message (chống query nặng vô ý).
- Unknown gateway → 404; slave không tồn tại → 404 riêng theo param.

### 4.5 Auth — điểm gắn sau (ghi chú bắt buộc)

Phase 1 **không enforce auth**, nhưng:
- Toàn bộ route đi qua `get_current_user` dependency **stub** (dev-mode trả user admin giả từ config). Khi bật auth chỉ cần thay implementation (JWT qua `POST /api/v1/auth/login` + `Authorization: Bearer`), không đổi các handler.
- WS: placeholder `?token=` check trong `deps` của WS route (tắt bằng env `AUTH_ENABLED=false`).
- Bảng `users` + `role` đã có sẵn schema (§3.1).

---

## 5. Cấu trúc thư mục & Docker

### 5.1 Cây thư mục

```
SignalBridge/
├── PROJECT_PLAN.md
├── README.md
├── .env.example
├── docker-compose.yml
├── .gitignore
├── docs/                                # xem §6
│   ├── payloads/
│   └── reports/
├── gateway_simulator/                   # firmware thật chưa cần; giả lập GW_S7200 để dev/test
│   └── simulator.py                     # publish đúng 5 loại payload theo báo cáo, env-driven
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/                         # migrations Postgres
│   │   └── versions/
│   ├── app/
│   │   ├── main.py                      # FastAPI app + startup: spawn MQTT listener task
│   │   ├── config.py                    # pydantic-settings, đọc env
│   │   ├── deps.py                      # stub auth, get stores
│   │   ├── parsers/
│   │   │   ├── base.py                  # models + GatewayAdapter ABC
│   │   │   ├── registry.py
│   │   │   └── s7200_v1.py
│   │   ├── ingestion/
│   │   │   ├── mqtt_client.py           # subscribe devices/+/+, reconnect, dispatch
│   │   │   └── pipeline.py              # normalized msg → stores (influx/pg/redis) + broadcaster
│   │   ├── stores/
│   │   │   ├── postgres.py
│   │   │   ├── influx.py
│   │   │   └── redis_client.py          # latest cache + last_seen + helpers badge
│   │   ├── api/
│   │   │   ├── health.py
│   │   │   ├── dashboard.py
│   │   │   ├── gateways.py
│   │   │   └── events.py
│   │   ├── ws/
│   │   │   ├── hub.py                   # Broadcaster interface + Local/Redis impls
│   │   │   └── routes.py
│   │   └── logging_config.py
│   └── tests/
│       ├── test_parsers_s7200.py        # theo các case ở §2.4
│       ├── test_pipeline.py
│       └── test_api.py                  # httpx + testcontainers (pg/influx/redis)
└── frontend/
    ├── Dockerfile
    ├── nginx.conf                       # proxy /api, /ws → backend
    ├── package.json  tsconfig.json  vite.config.ts
    └── src/
        ├── main.tsx  App.tsx
        ├── api/
        │   ├── client.ts                # fetch wrapper
        │   └── ws.ts                    # useGatewaySocket hook (reconnect + backoff)
        ├── types/api.ts                 # mirrors §4 contracts
        ├── components/
        │   ├── StatusBadge.tsx          # online / stale / offline (3 trạng thái)
        │   ├── GatewayCard.tsx
        │   ├── SignalGauge.tsx
        │   └── TelemetryChart.tsx       # Recharts
        └── pages/
            ├── DashboardPage.tsx        # milestone 6
            ├── GatewayDetailPage.tsx    # milestone 7
            └── admin/GatewaysAdminPage.tsx  # milestone 8 (Q8): đăng ký/sửa/gỡ gateway
```

### 5.2 docker-compose.yml (đầy đủ)

```yaml
name: signalbridge
services:
  emqx:
    image: emqx:5
    ports: ["1883:1883", "8083:8083", "18083:18083"]   # 18083 = dashboard EMQX
    environment: { EMQX_DASHBOARD__DEFAULT_PASSWORD: "${EMQX_DASHBOARD_PASSWORD}" }
    volumes: [ emqx_data:/opt/emqx/data, emqx_log:/opt/emqx/log ]
    healthcheck: { test: ["CMD", "/opt/emqx/bin/emqx", "ctl", "status"], interval: 10s, retries: 5 }

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-signalbridge}
      POSTGRES_USER: ${POSTGRES_USER:-sb}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?required}
    volumes: [ pg_data:/var/lib/postgresql/data ]
    ports: ["5432:5432"]          # bỏ khi lên prod
    healthcheck: { test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-sb}"], interval: 5s }

  influxdb:
    image: influxdb:2.7
    environment:
      DOCKER_INFLUXDB_INIT_MODE: setup
      DOCKER_INFLUXDB_INIT_USERNAME: ${INFLUX_USER:-sb-admin}
      DOCKER_INFLUXDB_INIT_PASSWORD: ${INFLUX_PASSWORD:?required}
      DOCKER_INFLUXDB_INIT_ORG: ${INFLUX_ORG:-signalbridge}
      DOCKER_INFLUXDB_INIT_BUCKET: ${INFLUX_BUCKET:-plc}
      DOCKER_INFLUXDB_INIT_RETENTION: 60d
      DOCKER_INFLUXDB_INIT_ADMIN_TOKEN: ${INFLUX_TOKEN:?required}
    volumes: [ influx_data:/var/lib/influxdb2 ]
    ports: ["8086:8086"]

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    volumes: [ redis_data:/data ]
    ports: ["6379:6379"]

  backend:
    build: ./backend
    env_file: .env
    environment:
      DATABASE_URL: postgresql+asyncpg://...://postgres:5432/${POSTGRES_DB}
      INFLUX_URL: http://influxdb:8086
      REDIS_URL: redis://redis:6379/0
      MQTT_HOST: emqx
      MQTT_PORT: "1883"
      MQTT_TOPIC_FILTER: devices/+/+
      STALE_THRESHOLD_S: "10"
      WS_TELEMETRY_MIN_INTERVAL_MS: "250"
      AUTH_ENABLED: "false"
    depends_on: { postgres: {condition: service_healthy}, redis: {condition: service_started},
                  influxdb: {condition: service_started}, emqx: {condition: service_healthy} }
    ports: ["8000:8000"]
    command: sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"

  frontend:
    build: ./frontend
    depends_on: [backend]
    # không expose — chỉ nginx vào

  nginx:
    image: nginx:1.27-alpine
    volumes:
      - ./deploy/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    ports: ["80:80"]
    depends_on: [backend, frontend]

volumes: { pg_data: {}, influx_data: {}, redis_data: {}, emqx_data: {}, emqx_log: {} }
```

`deploy/nginx/nginx.conf`: `/api/` → `backend:8000`; `/ws` → `backend:8000` với `proxy_http_version 1.1; proxy_set_header Upgrade/Connection; proxy_read_timeout 3600s`; `/` → `frontend:80`.

`.env.example` khai báo: `POSTGRES_PASSWORD`, `INFLUX_PASSWORD`, `INFLUX_TOKEN`, `EMQX_DASHBOARD_PASSWORD`, `STALE_THRESHOLD_S`, `AUTH_ENABLED`. Secrets không commit; `.env` vào `.gitignore`.

---

## 6. Quy ước quản lý `/docs` & báo cáo — **đã khởi tạo 2026-09-19**

```
docs/
├── README.md                     # hướng dẫn cấu trúc + vòng lặp làm việc
├── payloads/                     # ground truth từ gateway/firmware — chỉ thêm, không sửa về sau
│   └── BAO_CAO_PAYLOAD_Gateway_S7200.md
└── reports/
    ├── REPORT_OVERVIEW.md        # ⭐ FILE TIẾN TRÌNH TỔNG QUAN — đọc ĐẦU TIÊN mỗi phiên, cập nhật mỗi commit kết thúc phase
    ├── templates/
    │   └── phase_report.md       # template báo cáo chi tiết theo phase/chức năng
    └── <M_ID>-<slug>.md          # vd M02-mqtt-ingestion.md — MỖI phase/1 chức năng 1 file
```

Quy tắc bắt buộc:
1. **Quy tắc "đọc docs trước"** được đặt trong **`AGENTS.md`** ở gốc repo (nạp tự động đầu mỗi phiên làm việc): đọc `docs/reports/REPORT_OVERVIEW.md` → `PROJECT_PLAN.md` → báo cáo phase liên quan → `docs/payloads/` trước khi làm bất kỳ việc gì.
2. **Kết thúc mỗi phase (milestone) hoặc hoàn thành 1 chức năng độc lập** → tạo `docs/reports/<M_ID>-<ten-slug>.md` theo template: *Mục tiêu / Task đã thực hiện / Bảng kiểm chứng DoD (lệnh + output thực tế) / Phát hiện mới so với plan / Tồn đọng & rủi ro / Câu hỏi mới / Ảnh hưởng tới tài liệu*.
3. **Cập nhật `docs/reports/REPORT_OVERVIEW.md` trong cùng commit** — file gồm: bảng trạng thái 8 milestone (kèm link báo cáo), các quyết định đã chốt (kèm ngày), câu hỏi mở còn lại, rủi ro theo dõi, nhật ký cập nhật. Đây là file trạng thái nguồn-một-chốn; nếu nó mâu thuẫn code thì sửa nó cho khớp thực tế.
4. Payload mẫu của **gateway loại mới** phải được lưu vào `docs/payloads/` **trước khi** viết adapter cho nó (đúng tinh thần §2).
5. Tài liệu không được là nguồn chân lý duy nhất: mọi contract trong plan (API, schema) phải có test tương ứng để phát hiện drift.

---

## 7. Milestones

> Mỗi milestone kết thúc bằng: code merge vào `main` (qua PR), báo cáo `docs/reports/` theo §6, cập nhật `REPORT_OVERVIEW.md`.

### M0 — Scaffolding repo & tài liệu nền tảng
**Mục tiêu:** khung repo chạy được, không có chức năng nghiệp vụ.
**Tasks:** tạo cấu trúc thư mục §5.1; `requirements.txt`/`package.json` pin version; `.env.example`; `.gitignore`; `README.md` (cách chạy); ~~template báo cáo + `REPORT_OVERVIEW.md` khởi tạo~~ (đã làm 2026-09-19 — M0 chỉ đối chiếu khớp thực tế); ruff/black/pytest + eslint/prettier; CI GitHub Actions (lint + test, build image).
**DoD:** `git clone` → theo README chạy `npm run dev` (frontend) và `pytest` (backend, chỉ test rỗng pass) không lỗi; CI xanh; 2 file docs đầu tiên tồn tại.

### M1 — Hạ tầng Docker
**Mục tiêu:** toàn bộ stack chạy bằng 1 lệnh.
**Tasks:** viết `docker-compose.yml` §5.2 + nginx.conf; migrate alembic baseline (schema §3.1); seed 1 user admin + gateway mẫu `GW_S7200_01` (adapter_key `s7200_v1`); healthcheck cho từng service; **công bố IP:port EMQX của máy chủ compose cho team firmware để cập nhật broker trên gateway (Q1 đã chốt: firmware đổi IP)**.
**DoD:** `docker compose up -d` → 7 service `healthy/running`; `curl localhost/api/v1/health` trả `{"status":"ok"}` kèm pg/influx/redis/mqtt đều `connected`; `mosquitto_sub` (hoặc `docker exec`) subscribe `devices/+/+` không lỗi; EMQX dashboard truy cập được port 18083; bảng pg tạo đúng theo DDL (`\dt` đối chiếu plan); IP broker mới đã gửi cho team firmware (ghi vào báo cáo sprint).

### M2 — Kết nối MQTT & xác nhận payload (chưa lưu)
**Mục tiêu:** pipeline nhận message thật (hoặc simulator) và chứng minh payload khớp báo cáo.
**Tasks:** `gateway_simulator/simulator.py` phát lại đúng 5 loại payload theo §3 plan (kèm biến thể: thiếu `hr_54`, LWT offline, retain info); `mqtt_client.py` subscribe + reconnect; adapter `s7200_v1` parse + log NormalizedMessage dạng JSON đẹp ra console; metric `parse_errors`; unit tests parser §2.4.
**DoD:** bật simulator 60 s → log backend hiển thị đủ 5 loại message, đúng số field theo báo cáo (telemetry 8 DI + ai_raw, **không có** `hc0`/`c0` khi region chưa mở — khớp rủi ro #6); kill simulator → nhận frame status LWT offline trong log < 5 s; `pytest tests/test_parsers_s7200.py` xanh; **nếu có gateway thật**: chạy song song simulator, diff log với mục 1–5 của báo cáo, kết quả ghi vào báo cáo sprint.

### M3 — Persist vào 3 kho
**Mục tiêu:** dữ liệu vào InfluxDB, Postgres, Redis đúng như §3.
**Tasks:** influx writer (batch 1 s, sparse field); redis writer (`latest`, `status`, `last_seen`); pg writer: upsert gateways/slaves từ `info`, insert events từ `event` + chuyển tiếp `status` thành event `STATUS_ONLINE/OFFLINE` (dedupe: chỉ ghi khi state đổi); diag → Influx measurement `diag`; idempotency khi broker replay retain.
**DoD:** simulator chạy 10 phút → (a) `influx query` đếm `telemetry` points ≈ 100/s ±10% cho mỗi slave có đủ field; (b) `redis-cli HGETALL sb:latest:GW_S7200_01:1` có `_received_at` khớp thời điểm server (không phải `ts`); (c) `SELECT` trên `gateway_events` có đúng 2 dòng STATUS khi kill/restart simulator (không spam); (d) slaves được upsert từ `info`; (e) kill -9 backend giữa dòng rồi restart → retain replay không tạo event trùng.

### M4 — REST API đọc dữ liệu
**Mục tiêu:** các endpoint §4.1 hoạt động với dữ liệu simulator.
**Tasks:** dashboard/summary (tính badge 3 trạng thái theo §3.3), gateways CRUD tối thiểu (đọc + patch `enabled`), latest, history (Flux), events phân trang, diag; logic `scaled=false` khi chưa có công thức scale; tests httpx cho từng endpoint (kể cả trường hợp thiếu field `hc0`).
**DoD:** mọi ví dụ JSON §4.1 đạt được bằng `curl` với dữ liệu simulator (so sánh bằng test snapshot); endpoint summary trả `badge:"stale"` khi dừng telemetry nhưng chưa kill kết nối MQTT, trả `"offline"` sau khi broker phát LWT; `/api/v1/health` reflect trạng thái từng store; coverage test API > 80%.

### M5 — WebSocket realtime
**Mục tiêu:** frontend có thể subscribe dữ liệu sống.
**Tasks:** WS hub + subscribe protocol §4.2; throttle `WS_TELEMETRY_MIN_INTERVAL_MS`; snapshot khi connect; ping/heartbeat 30 s; switch `Broadcaster` sang Redis Pub/Sub khi env bật; e2e test bằng `websockets` client.
**DoD:** client test connect → nhận `snapshot` ngay, nhận `telemetry` với nhịp ≈ throttle đã cấu hình (đo trong 10 s, sai số ±10%); kill simulator → frame `status offline` tới client < 5 s; restart backend → client reconnect nhận snapshot mới; với `WS_TELEMETRY_MIN_INTERVAL_MS=250`, CPU backend tăng không đáng kể (<5% so với M4).

### M6 — Frontend dashboard tổng quan
**Mục tiêu:** trang chủ nhìn thấy toàn bộ nhà máy.
**Tasks:** `api/client.ts` + `useGatewaySocket` hook (reconnect/backoff); `StatusBadge` 3 trạng thái với tooltip giải thích (online / dữ liệu trễ / offline — ràng buộc #5); `GatewayCard` hiển thị primary metrics + chú thích "(raw)" khi `scaled=false`; summary page render danh sách card, cập nhật realtime qua WS; skeleton/loading/error states; build qua Docker + Nginx.
**DoD:** mở `http://localhost/` → thấy card `GW_S7200_01` online, giá trị `ai_raw` cập nhật liên tục; dùng simulator: dừng gửi telemetry (giữ kết nối MQTT) → badge chuyển `stale` trong ≤ `STALE_THRESHOLD_S` + 1 nhịp UI; kill kết nối MQTT → badge `offline` (LWT) < 5 s; đóng/mở tab nhiều lần không leak WS (devtools network); `npm run build` không lỗi TS strict.

### M7 — Frontend chi tiết từng gateway/slave
**Mục tiêu:** drill-down theo gateway → slave.
**Tasks:** route `/gateways/:id`; trang chi tiết: header meta (fw/hw/ip/mac/slaves — nguồn `info`), tab Telemetry (chart Recharts chọn signal + khoảng thời gian, gọi `/history`), tab Events (bảng phân trang), tab Diag (bảng thống kê + gap `seq` ước tính); per-slave selector (hỗ trợ n slave); WS cập nhật chart đang hiển thị.
**DoD:** chọn signal `ai_raw` khoảng 1 h, chart render < 1 s, có đủ điểm (đếm so với influx CLI); bảng events khớp DB; chart hiển thị đúng gap khi simulator phát biến thể thiếu `hc0` (đường đứt đoạn, không crash); responsive ≥ 1280px; mọi case lỗi (gateway 404, influx timeout) hiển thị thông báo, không white-screen.

### M8 — Admin UI đăng ký & quản lý gateway (Q8)
**Mục tiêu:** thêm/sửa/gỡ gateway mà không đụng SQL.
**Tasks:** hoàn thiện `POST/PATCH/DELETE /api/v1/gateways` (§4.1) + tests (409 trùng id, 422 adapter_key lạ, validate `gateway_id`); trang `admin/GatewaysAdminPage.tsx`: bảng gateways (link sang trang chi tiết M7), form thêm gateway, form sửa inline, nút enable/disable, xác nhận trước xóa; hành vi khi xóa: giữ dữ liệu Influx, dọn key Redis, cascade Postgres; gateway **chưa đăng ký** mà vẫn publish MQTT → listener log WARN "unknown gateway" + hiển thị ở trang admin dạng "chưa đăng ký" (danh sách `gateway_id` thấy trên broker, chưa có trong DB) để admin bấm thêm nhanh.
**DoD:** quy trình E2E bằng đúng UI: thêm `GW_S7200_02` (simulator instance thứ 2) → gateway xuất hiện trên dashboard trong ≤ 15 s với badge đúng; disable → card ẩn khỏi summary nhưng history/events còn xem được; xóa → key Redis biến mất, dữ liệu Influx còn; thêm trùng id → thông báo lỗi 409 hiển thị thân thiện, không white-screen; toàn bộ thao tác admin nằm trong 1 trang, không cần SQL.

**Backlog sau M8 (không cam kết phase 1):** auth JWT thật (chặn các route POST/PATCH/DELETE), cảnh báo rules engine, alerting email/SMS, dashboard chế độ toàn màn hình xưởng, multi-user preferences.

---

## 8. Rủi ro & câu hỏi mở (cần xác nhận trước/song song khi code)

| # | Câu hỏi / rủi ro | Liên quan | Cần ai xác nhận | Chặn milestone nào |
|---|---|---|---|---|
| Q1 | ~~EMQX thay Mosquitto tại 192.168.1.4 hay broker mới?~~ **ĐÃ TRẢ LỜI (2026-09-19): broker mới (EMQX trên máy chủ compose) + firmware đổi IP.** Việc còn lại: cung cấp IP broker mới cho team firmware, lên lịch update từng gateway. | §1.3 | Team firmware thực hiện đổi IP | Không chặn M0–M7 (dùng simulator; đổi firmware là việc song song) |
| Q2 | **Công thức scale `ai_raw` → RPM** (hệ số a/b hoặc lookup table, dải 0–27648 của AIW0?) và tương tự `hc0`, `c0` (đơn vị counter là gì). **Quyết định tạm (2026-09-19): display raw** — API trả `value=raw, scaled=false, unit=null`, frontend gắn nhãn "(raw)". **Không đoán hệ số.** | §2.3, §4.1 | Team hardware (công thức cuối cùng) | Không chặn — chỉ chặn bước hiển thị đơn vị thật sau này |
| Q3 | Mở rộng region poll để lấy `hr_54`/`hr_58`? **ĐÃ TRẢ LỜI (2026-09-19): không chặn — chấp nhận `hc0`/`c0` vắng mặt; parser xử lý thiếu field. Khi nào firmware mở region là việc sau này.** | Rủi ro #6 báo cáo | — | Không chặn |
| Q4 | Các gateway loại khác có cùng schema? **ĐÃ TRẢ LỜI (2026-09-19): có — cùng loại payload** → dùng lại adapter `s7200_v1`; adapter pattern vẫn giữ cho loại khác tương lai. | §2 | — | Không chặn |
| Q5 | Retention InfluxDB? **ĐÃ TRẢ LỜI (2026-09-19): 60 ngày** (§3.2, compose `INIT_RETENTION: 60d`). | §3.2 | — | — |
| Q6 | Chu kỳ poll / ngưỡng stale? **ĐÃ TRẢ LỜI (2026-09-19): demo giữ mặc định 10 s (env `STALE_THRESHOLD_S`), điều chỉnh sau nếu cần.** | §3.3 | — | Không chặn |
| Q7 | `diag.tx_packets`/`tx_failures` semantics sai (rủi ro #2) — gắn nhãn hay ẩn? ⏳ **CHƯA TRẢ LỜI** — tạm hiển thị kèm chú thích "biến đếm Modbus, không phải MQTT TX". | §3.2 Influx diag | UX + team firmware | Không chặn |
| Q8 | Đăng ký gateway mới? **ĐÃ TRẢ LỜI (2026-09-19): qua UI admin** → thêm endpoints gateway CRUD (§4.1) + **milestone M8 — Admin UI**. | §3.1, §4.1, §7 M8 | — | Không chặn M0–M7 |
| R1 | Telemetry QoS 0 mất gói mạng không phát hiện được đầy đủ (rủi ro #8) → gap `seq` chỉ là ước lượng khi broker vẫn nhận. Đã chấp nhận ở phase 1; nếu cần toàn vẹn thì đổi telemetry sang QoS 1 ở firmware. | §3.3 | Review cùng firmware | — |
| R2 | `reset_reason` cứng `"POWER_ON"` (rủi ro #3) → không dùng làm tín hiệu restart; backend tính "số lần online lại" từ chuỗi STATUS events trong `gateway_events`. | §3.1 | — | — |

---

## 9. Definition of Done toàn cục (phase 1)

Phase 1 hoàn thành khi: M0–M8 xong DoD tương ứng; chạy được toàn bộ bằng `docker compose up` + truy cập qua Nginx port 80; một gateway thật (GW_S7200_01) hiển thị online + dữ liệu realtime trên dashboard phân biệt được 3 badge trạng thái; gateway thứ hai được đăng ký thành công qua UI admin (không dùng SQL); mọi báo cáo sprint + `REPORT_OVERVIEW.md` nằm trong `docs/reports/`; các câu hỏi còn mở (hiện chỉ còn Q2 công thức scale cuối cùng, Q7) đã có người phụ trách và câu trả lời được phản ánh vào plan (update phiên bản file này nếu thiết kế đổi).
