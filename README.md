# SignalBridge — Giám sát PLC realtime

Web app giám sát realtime dữ liệu PLC qua gateway MQTT. Thiết kế chi tiết: [`PROJECT_PLAN.md`](PROJECT_PLAN.md) · Tiến trình: [`docs/reports/REPORT_OVERVIEW.md`](docs/reports/REPORT_OVERVIEW.md).

## Bắt đầu làm việc (đọc theo thứ tự)

1. `docs/reports/REPORT_OVERVIEW.md` — đang ở milestone nào, quyết định đã chốt, câu hỏi mở.
2. `PROJECT_PLAN.md` — thiết kế + milestones + DoD.
3. `docs/payloads/` — ground truth payload từ gateway.
4. `AGENTS.md` — quy tắc bắt buộc với agent/collaborator.

## Chạy local

Yêu cầu: Python ≥ 3.12, Node ≥ 22, Docker + Docker Compose.

```bash
cp .env.example .env        # đổi các giá trị change-me (secret)

docker compose up -d --build   # 7 service: emqx, postgres, influxdb, redis, backend, frontend, nginx
curl http://localhost/api/v1/health   # {"status":"ok","checks":{...}}
# UI: http://localhost/  ·  EMQX dashboard: http://localhost:18083  ·  API docs: http://localhost:8000/docs
```

Dev mode không cần compose cho backend/frontend:

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
uvicorn app.main:app --reload            # /health sẽ degraded nếu stores chưa chạy — bình thường

# Frontend
cd frontend
npm install                              # lưu ý: npm cục bộ chặn postinstall esbuild → `npm install-scripts approve esbuild`
npm run dev                              # http://localhost:5173
```

## Cấu trúc

```
backend/            FastAPI: parsers/ ingestion/ stores/ api/ ws/
frontend/           React + TS + Vite (Recharts, lucide-react)
gateway_simulator/  Giả lập GW_S7200_01 publish MQTT
deploy/             nginx compose-level (M1)
docs/               payloads/ (ground truth) + reports/ (tiến trình)
```

## Gateway simulator (dev/test M2+)

```bash
cd backend && source .venv/bin/activate && pip install -r ../gateway_simulator/requirements.txt
python ../gateway_simulator/simulator.py --host 192.168.1.3 --duration 60 --diag-interval-s 5
# --with-hr54   : giả lập firmware đã mở region 54–58 (hr_54/hr_58 xuất hiện)
# --fail-rate X : phát event SLAVE_COMM_LOST (rate-limit 30 s như firmware)
# kill -9       : test LWT offline (~3 s với --keepalive 2 mặc định)
# Theo dõi: docker compose logs -f backend | grep NORMALIZED
```

## Dữ liệu đi đâu (M3)

Pipeline `mqtt → parser → persist` ghi 3 kho; mọi timestamp là **server receive time** (`ts` payload = 0, bỏ qua):

| Kho | Nội dung | Xem nhanh |
|---|---|---|
| InfluxDB bucket `plc` | measurement `telemetry` (tags gateway/slave/adapter, fields sparse) + `diag` | `docker compose exec influxdb influx query --token "$INFLUX_TOKEN" --org signalbridge 'from(bucket:"plc")\|>range(start:-5m)\|>filter(fn:(r)=>r._measurement=="telemetry")\|>limit(n:5)'` |
| Redis | `sb:latest:{gw}:{slave}` (hash signals + `_received_at`,`_seq`), `sb:status:{gw}`, `sb:last_seen:{gw}` | `docker compose exec redis redis-cli HGETALL sb:latest:GW_S7200_01:1` |
| Postgres | `gateways`/`slaves` (upsert từ `info`), `gateway_events` (event + STATUS_ONLINE/OFFLINE chỉ khi đổi trạng thái) | `docker compose exec postgres psql -U sb -d signalbridge -c "SELECT * FROM gateway_events ORDER BY id DESC LIMIT 10"` |

Counter lỗi ghi + số điểm đã flush: `curl localhost/api/v1/ingestion/stats`.

## REST API (M4)

Tất cả qua Nginx tại `http://localhost/api/v1` (khái quát: `PROJECT_PLAN.md` §4.1):

```
GET  /dashboard/summary                 # badge online/stale/offline + primary metrics (raw, scaled=false)
GET  /gateways                          # danh sách + meta (fw/ip/mac từ info) + slaves
GET  /gateways/{id}[/latest|/history|/events|/diag]
     ?signals=ai_raw,hc0&agg=10s&from=...&to=...   # history: window ≤ 7 ngày, agg raw|duration; vượt limit giữ điểm MỚI NHẤT (M8)
GET  /events?limit=200&before=...       # aggregate toàn hệ thống 1 request (M8), con trỏ next_before
POST   /gateways                        # đăng ký gateway mới {gateway_id, adapter_key, display_name?} → 201 | 400 | 409 | 422 (M8)
GET  /gateways/unknown                  # gateway thấy trên broker nhưng chưa có row DB (M8)
GET  /adapters                          # danh sách adapter_key trong registry (M8)
DELETE /gateways/{id}                   # xóa cascade PG + dọn key Redis (scan `sb:latest:{id}:*`), Influx giữ (M8)
PATCH /gateways/{id}                    # display_name | adapter_key | enabled
```

Lỗi trả `{"error": {"code": "...", "message": "..."}}` (404 gateway_not_found / slave_not_found, 400 range_too_large, 503 store_unavailable).

## WebSocket realtime (M5)

`ws://localhost/ws` (qua Nginx). Client gửi `{"type":"subscribe","gateways":["GW_S7200_01"]}` — thiếu `gateways` = nhận hết. Server trả envelope `{"type","ts","data"}` với kind: `snapshot` (frame đầu khi connect — summary §4.1), `telemetry` (throttle latest-wins `WS_TELEMETRY_MIN_INTERVAL_MS=250`), `status`/`event`/`info`/`diag` (gửi ngay). Heartbeat: uvicorn protocol ping 30 s. Nhiều instance backend: bật `WS_PUBSUB_ENABLED=true` (fan-out Redis Pub/Sub kênh `sb:ws`). Đo nhanh: `cd backend && python tests/e2e_ws.py rate|wait|hold --url ws://localhost:8000/ws` (cần `pip install websockets`).

## Dashboard (M6 + M6b redesign + M7 chi tiết + M8 admin)

Giao diện dark theo tham chiếu admin IIoT: topbar (chip live WS) + sidebar, 6 route — `/` (KPI + card gateway có sparkline), `/gateways/:id` (breadcrumb, meta fw/hw/ip/mac, bảng PLC badge per-slave, panel cảnh báo), `/gateways/:id/slaves/:addr` (chart Recharts tầm nhìn 15m/1h/6h/24h qua `/history`), `/events` (lọc severity/device/code + phân trang, nút "Tải thêm (cũ hơn)" dùng con trỏ `before`), `/diagnostics` (bảng `/diag` + lịch sử diag từ frame WS + cột seq gap 1h ước lượng mất gói QoS 0), `/admin` (quản trị gateway — xem M8 bên dưới); route lạ → trang 404.

M7: trang slave chọn từng signal (pills), trục thời gian hợp nhất — signal vắng tại mốc nào (vd `hc0` khi firmware không poll region 54–58) → đường đứt đoạn tại đó; WS stream nối vào đuôi chart đang xem giữa hai lần REST 15 s.

M8: route `/admin` (sidebar "Quản trị → Gateway") — quản lý gateway không cần SQL: bảng gateways (link chi tiết), form thêm gateway (chọn adapter từ `/adapters`), sửa `display_name` inline, nút tắt/bật (`enabled`), xóa có xác nhận (PG cascade + dọn Redis, Influx giữ), panel "chưa đăng ký" từ telemetry lạ trên broker với nút thêm nhanh; lỗi 400/409/422 hiển thị thông báo thân thiện. Trang `/events` từ M8 dùng `GET /api/v1/events` aggregate (một request thay lặp theo gateway).

Nguồn dữ liệu: REST seed lúc tải trang, sau đó **một socket WS dùng chung mọi route** (`LiveProvider`) cập nhật realtime — snapshot + telemetry throttle 250 ms + status/event/info/diag; tự reconnect backoff 1→30 s. Badge mỗi gateway tính phía client mỗi giây (broker state × độ tươi telemetry, ngưỡng `STALE_THRESHOLD_S=10`); badge slave lấy max(REST /latest, mốc WS cuối) để không nhấp trễ giả giữa 2 lần refresh; giá trị analog hiển thị raw + nhãn "(raw)" chờ Q2b. Trang GatewayDetail/SlaveDetail có auto-refresh REST (5 s / 15 s). Dev mode: `cd frontend && npm run dev` → `http://localhost:5173` (vite proxy sẵn `/api` và `/ws` sang `:8000`).
