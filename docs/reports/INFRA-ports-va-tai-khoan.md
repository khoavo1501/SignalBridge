# Báo cáo hạ tầng — Cổng (ports) & tài khoản truy cập

- **Ngày cập nhật:** 2026-09-19 (sau M6b)
- **Phạm vi:** toàn bộ stack SignalBridge (docker-compose) + môi trường dev
- **Nguyên tắc secrets:** file này KHÔNG chứa mật khẩu thật. Giá trị secrets nằm trong `.env` ở gốc repo (đã gitignore — không bao giờ commit). Mỗi hàng dưới đây trỏ đúng tên biến trong `.env`.

## 1. Bảng cổng (ports)

### Public trên máy host

| Cổng | Service | Lắng nghe | Dùng để | Truy cập từ |
|---|---|---|---|---|
| **80** | nginx | `0.0.0.0:80` | **Điểm vào chính của app**: `/` → frontend, `/api/` → backend, `/ws` → WebSocket (proxy_read_timeout 3600 s) | mọi máy trong LAN (`http://192.168.1.3/` hoặc host name) |
| **8000** | backend (uvicorn) | `0.0.0.0:8000` | REST `/api/v1/...` + WS `/ws` trực tiếp không qua nginx (debug, e2e script `tests/e2e_ws.py`) | host / LAN |
| **1883** | EMQX | `0.0.0.0:1883` | **MQTT cho gateway/firmware** — broker bàn giao Q1: `192.168.1.3:1883`; simulator cũng publish vào đây | firmware + LAN |
| 8083 | EMQX | `0.0.0.0:8083` | MQTT over WebSocket (chưa dùng tới — để sẵn cho gateway qua web) | LAN |
| 18083 | EMQX | `0.0.0.0:18083` | Dashboard quản trị EMQX | host (`http://localhost:18083`) |
| 5432 | PostgreSQL | `0.0.0.0:5432` | DB quan hệ (gateways, events, status history) — expose cho debug | host |
| 8086 | InfluxDB 2.7 | `0.0.0.0:8086` | Time-series (telemetry, diag) + UI admin | host (`http://localhost:8086`) |
| 6379 | Redis 7 | `0.0.0.0:6379` | Key nóng `sb:latest` / `sb:status` / `sb:last_seen` (+ Pub/Sub `sb:ws` khi bật `WS_PUBSUB_ENABLED`) | host |
| 5173 | vite dev | chỉ khi `npm run dev` | Frontend dev mode, proxy sẵn `/api` + `/ws` sang `:8000` | host |

### Nội bộ docker network (không publish ra host)

| Endpoint | Ghi chú |
|---|---|
| `backend:8000` | nginx upstream `backend_up` |
| `frontend:80` | nginx upstream `frontend_up` (chỉ `expose`, không publish — mọi truy cập qua nginx :80) |
| `postgres:5432`, `influxdb:8086`, `redis:6379`, `emqx:1883` | backend nối theo service name qua `DATABASE_URL` / `INFLUX_URL` / `REDIS_URL` / `MQTT_HOST=emqx` |

## 2. Tài khoản truy cập

| Hệ thống | URL / lệnh | User | Mật khẩu / token | Ghi chú |
|---|---|---|---|---|
| **SignalBridge UI** | `http://localhost/` | — | — | Chưa có login (phase 1 không auth; JWT stub chờ gắn — plan §4.5) |
| **REST API** | `http://localhost/api/v1/...` | — | — | `AUTH_ENABLED=false` trong `.env`; bật `true` → WS/REST yêu cầu `?token=` (placeholder M8) |
| **EMQX dashboard** | `http://localhost:18083` | `admin` | `.env: EMQX_DASHBOARD_PASSWORD` | |
| **EMQX MQTT (device)** | `192.168.1.3:1883` | không | không | Listener mặc định **anonymous** (demo LAN nội bộ). Firmware/simulator không gửi credentials. Siết ACL khi production |
| **PostgreSQL** | `psql -h localhost -U sb signalbridge` (hoặc `docker compose exec postgres psql -U sb -d signalbridge`) | `sb` | `.env: POSTGRES_PASSWORD` | DB `signalbridge` (`POSTGRES_DB`) |
| **InfluxDB UI/API** | `http://localhost:8086` | `sb-admin` | `.env: INFLUX_PASSWORD` | Org `signalbridge`, bucket `plc`, retention 60 ngày (Q5). API token: `.env: INFLUX_TOKEN` |
| **Redis** | `redis-cli -p 6379` | — | — | **Không có password** — chỉ publish port trên host nội bộ, không mở ra ngoài |
| **Backend stats/health** | `http://localhost:8000/api/v1/health` · `/api/v1/ingestion/stats` | — | — | Endpoint mở, dùng monitor |

## 3. Biến môi trường vận hành (không phải secrets)

| Biến | Giá trị hiện tại | Ý nghĩa |
|---|---|---|
| `STALE_THRESHOLD_S` | 10 | ngưỡng badge "dữ liệu trễ" (Q6) |
| `WS_TELEMETRY_MIN_INTERVAL_MS` | 250 | throttle telemetry latest-wins (§4.2) |
| `WS_PUBSUB_ENABLED` | false | bật khi chạy nhiều backend instance |
| `AUTH_ENABLED` | false | stub JWT (§4.5, M8) |
| `MQTT_TOPIC_FILTER` | `devices/+/+` | backend subscribe; payload theo `docs/payloads/` |

## 4. Việc còn mở

- Secrets demo hiện sinh ngẫu nhiên, nằm gọn trong `.env` (gitignored). **Không** copy giá trị thật vào file này hoặc bất kỳ file nào được commit.
- Production: đóng bớt port publish (5432/6379/8086/1883 chỉ bind `127.0.0.1` hoặc docker network nội bộ), bật MQTT auth + ACL, đặt password Redis, bật `AUTH_ENABLED` + HTTPS (plan §4.5).
- EMQX dashboard user `admin` nên đổi sau lần đăng nhập đầu (khuyến nghị của EMQX).
