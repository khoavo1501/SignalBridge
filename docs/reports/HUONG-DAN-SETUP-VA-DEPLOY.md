# Hướng dẫn Setup & Deploy — SignalBridge

- **Ngày:** 2026-09-20 (sau M8, phase 1 hoàn thành 9/9)
- **Phạm vi:** từ clone repo → stack chạy đầy đủ → gateway thật/simulator vào hệ thống → vận hành hằng ngày → checklist production
- **Nguồn sự thật:** `docker-compose.yml`, `.env.example`, `deploy/nginx/nginx.conf`, `docs/reports/INFRA-ports-va-tai-khoan.md`, `README.md`. File này KHÔNG chứa secrets — mọi secret nằm trong `.env` (đã gitignore).

## 0. Yêu cầu nền tảng

| Thành phần | Phiên bản | Ghi chú |
|---|---|---|
| Docker + Docker Compose v2 | hiện tại | stack production-like chạy hoàn toàn trong compose |
| Python | ≥ 3.12 | chỉ cần cho dev mode; container backend dùng `python:3.12-slim`. **Lưu ý máy dev chạy Python 3.14 (Arch):** các pin cũ không có wheel cp314, `requirements*.txt` đã đóng băng theo version pip resolve — tạo venv bằng chính Python 3.14 đó là chạy được |
| Node | ≥ 22 | dev mode frontend |
| quyền mạng | lớp `192.168.1.x` | broker EMQX bàn giao Q1 = **`192.168.1.3:1883`** — máy deploy compose phải giữ IP này (hoặc cập nhật firmware/gateway theo IP mới) |

## 1. Setup lần đầu (deploy đầy đủ)

```bash
git clone <repo> && cd SignalBridge
cp .env.example .env
```

Sửa `.env` — bắt buộc đổi mọi giá trị `change-me*`:

| Nhóm | Biến |
|---|---|
| Postgres | `POSTGRES_PASSWORD` (`DATABASE_URL` phải đổi theo) |
| InfluxDB 2.x | `INFLUX_PASSWORD`, `INFLUX_TOKEN` (init **một lần** lúc volume trống — đổi token sau khi đã chạy sẽ làm backend lỗi ghi) |
| EMQX | `EMQX_DASHBOARD_PASSWORD` |
| Vận hành | `STALE_THRESHOLD_S=10`, `WS_TELEMETRY_MIN_INTERVAL_MS=250`, `WS_PUBSUB_ENABLED=false`, `AUTH_ENABLED=false`, `MQTT_TOPIC_FILTER=devices/+/+` |

```bash
docker compose up -d --build
```

Compose tự thứ tự hóa: emqx/postgres/influxdb/redis healthy → **backend chạy `alembic upgrade head` + `python -m app.scripts.seed` rồi mới uvicorn** (không cần migrate thủ công) → frontend + nginx.

Verify nhanh:

```bash
docker compose ps                                  # 7 service healthy
curl http://localhost/api/v1/health                # {"status":"ok","checks":{pg,influx,redis,mqtt...}}
curl http://localhost/api/v1/dashboard/summary     # danh sách gateway (rỗng nếu chưa có nguồn phát)
```

Mở trong trình duyệt: UI `http://localhost/` · API docs `http://localhost:8000/docs` · EMQX dashboard `http://localhost:18083` (user `admin`).

## 2. Cho dữ liệu chảy vào (simulator hoặc gateway thật)

**Gateway thật (firmware S7-200 qua gateway MQTT):** cấu hình broker `192.168.1.3:1883`, topic `devices/{gateway_id}/{slave}` theo `docs/payloads/`. Gateway loại `s7200_v1` **tự đăng ký** qua payload `info` (upsert vào Postgres ~1 s sau frame đầu). Gateway chưa đăng ký mà vẫn phát telemetry sẽ hiện ở panel "chưa đăng ký" của **`http://localhost/admin`** — bấm thêm nhanh, hoặc `POST /api/v1/gateways` (id regex `^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$`, adapter_key phải có trong `GET /api/v1/adapters`).

**Simulator (dev/test):**

```bash
cd backend && source .venv/bin/activate
pip install -r ../gateway_simulator/requirements.txt
python ../gateway_simulator/simulator.py --host 192.168.1.3 --gateway-id GW_S7200_01 --duration 3600
# --interval-ms 100 (mặc định) · --diag-interval-s 600 · --with-hr54 (fw mở region 54–58)
# --fail-rate X (event SLAVE_COMM_LOST) · kill -9 → test LWT offline ~3 s (--keepalive 2)
```

Theo dõi pipeline: `docker compose logs -f backend | grep NORMALIZED`.

## 3. Cổng & điểm vào (chi tiết: INFRA-ports-va-tai-khoan.md)

| Cổng | Dùng cho |
|---|---|
| **80** (nginx) | **điểm vào duy nhất của app**: `/` UI, `/api/` REST, `/ws` WebSocket (`proxy_read_timeout 3600s`) |
| 8000 | backend trực tiếp (debug, `tests/e2e_ws.py`) — production nên bỏ publish |
| 1883 / 8083 / 18083 | MQTT cho gateway / MQTT-WS / dashboard EMQX |
| 5432 · 8086 · 6379 | PG · Influx · Redis — đang mở cho debug, **production phải bind `127.0.0.1`** |

Frontend container chỉ `expose :80` nội bộ — mọi truy cập qua nginx.

## 4. Dev mode (không build image mỗi lần)

```bash
# Backend — cần stack stores chạy trước (docker compose up -d postgres influxdb redis emqx)
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest && uvicorn app.main:app --reload          # :8000

# Frontend — vite proxy sẵn /api + /ws sang :8000
cd frontend && npm install
npm install-scripts approve esbuild              # npm cục bộ chặn postinstall → bắt buộc sau khi clone
npm run dev                                      # http://localhost:5173
```

Loop kiểm tra frontend trước khi deploy:

```bash
cd frontend && npx prettier --write src && npx eslint src --max-warnings 0 && npm run build
docker compose build frontend && docker compose up -d frontend
```

## 5. Vận hành hằng ngày

| Việc | Lệnh |
|---|---|
| Xem log / restart backend | `docker compose logs -f backend` · `docker compose restart backend` |
| Counter lỗi ghi + điểm đã flush | `curl localhost/api/v1/ingestion/stats` |
| WS clients đang nối | `curl localhost:8000/api/v1/ingestion/stats` (mục ws) hoặc reconnect test bằng `python tests/e2e_ws.py hold --url ws://localhost:8000/ws` |
| Xóa/đổi gateway | UI `/admin` (PATCH display_name/adapter/enabled; DELETE xóa PG + Redis, **giữ Influx** theo Q5 retention 60 ngày) |
| Dữ liệu thô | `docker compose exec influxdb influx query -o signalbridge 'from(bucket:"plc")|>range(start:-5m)|>limit(n:5)'` (bucket tên là **`plc`**) · `docker compose exec redis redis-cli HGETALL sb:latest:GW_S7200_01:1` · `docker compose exec postgres psql -U sb -d signalbridge` |
| Chạy nhiều backend instance | bật `WS_PUBSUB_ENABLED=true` (fan-out Redis Pub/Sub kênh `sb:ws`), nginx `upstream backend_up` thêm server |
| Backup | volume `pg_data` (pg_dump), `influx_data` (influx backup), `redis_data` chỉ là cache — loss-tolerant |

## 6. Checklist trước khi công bố "xong deploy"

1. `docker compose ps` — đủ 7 service, backend healthy (healthcheck gọi `/api/v1/healthz`).
2. `/api/v1/health` trả `ok` với cả 4 checks (pg, influx, redis, mqtt).
3. Simulator hoặc gateway thật phát ≥ 1 phút → UI `/` có badge **online**, giá trị analog đổi nhịp 250 ms, nhãn "(raw)" (Q2b chưa chốt công thức scale — **đừng đoán**).
4. Ngắt nguồn phát → badge chuyển **stale** sau `STALE_THRESHOLD_S=10` s; kill EMQX connection (LWT) → **offline** < 5 s.
5. Trang `/gateways/{id}/slaves/{addr}` cửa sổ 1h: chart trượt đều, không giật (agg backend 5s = 720 điểm).
6. `/admin` thêm/xóa được gateway test, `GET /gateways/unknown` hoạt động.

## 7. Hardening cho production (còn mở — ghi nhận từ INFRA §4)

- [ ]Bind 5432/6379/8086/1883 về `127.0.0.1` hoặc bỏ publish; chỉ giữ :80 (+ :1883 cho firmware).
- [ ]EMQX: tắt anonymous, bật auth + ACL theo topic `devices/{gw}/{slave}`; đổi mật `admin` dashboard.
- [ ]Redis: đặt password (`requirepass`) + cập nhật `REDIS_URL`.
- [ ]HTTPS + auth: `AUTH_ENABLED=true` (JWT stub đã định vị chỗ gắn — plan §4.5), đổi secret `INFLUX_TOKEN` qua UI Influx và khởi tạo lại volume nếu token demo đã lộ.
- [ ]CI: repo **chưa có git remote** — workflow `.github/workflows/ci.yml` chỉ chạy thật sau khi push.

## 8. Sự cố đã gặp & cách xử lý (troubleshooting)

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Backend lỗi Influx 401 sau khi đổi `.env` | Influx init token **một lần** lúc volume trống | đổi `INFLUX_TOKEN` trong `.env` = token thật trong UI Influx, hoặc `docker compose down -v` để init lại (mất dữ liệu) |
| Query influx CLI "không trả gì" | sai bucket/org — lỗi bị `2>/dev/null` che | dùng `-o signalbridge`, `bucket:"plc"` |
| `npm run dev`/build fail sau clone | npm cục bộ chặn postinstall esbuild | `npm install-scripts approve esbuild` |
| `pip install` fail trên máy Arch | Python 3.14 không có wheel các pin cũ | dùng `requirements*.txt` đã đóng băng; container không ảnh hưởng (3.12) |
| Redis key `sb:latest:*` còn sót sau DELETE gateway | client của slave chưa từng có row trong PG | đã fix M8: xóa theo `scan_iter("sb:latest:{gw}:*")` |
| Badge "trễ" nhấp nháy trên trang slave | REST refresh 15 s > ngưỡng 10 s | đã fix M7: `lastSeen = max(REST /latest, mốc WS cuối)` |
| Firmware không vào được broker | máy deploy đổi IP | EMQX bàn giao tại `192.168.1.3:1883` (Q1) — giữ IP hoặc đổi cấu hình firmware |
