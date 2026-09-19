# Báo cáo — M1: Hạ tầng Docker

- **Ngày hoàn thành:** 2026-09-19
- **Trạng thái:** ✅ Done
- **Commit/PR:** `63cb951` feat: M1 docker infra (main, chưa có remote)

## 1. Mục tiêu (PROJECT_PLAN.md §7 M1)

Toàn bộ stack chạy bằng 1 lệnh.

## 2. Task đã thực hiện

- [x] `docker-compose.yml` — 7 service: emqx, postgres, influxdb (retention 60d), redis (AOF), backend (build), frontend (build), nginx; healthcheck đầy đủ; env qua `.env`
- [x] `deploy/nginx/nginx.conf` — `/api/` → backend:8000, `/ws` → backend (upgrade headers, read_timeout 3600s), `/` → frontend:80
- [x] Alembic async: `alembic/env.py` (đọc `DATABASE_URL` từ env) + baseline `0001_baseline.py` đúng schema §3.1 (5 bảng + 2 index + unique constraints + FK cascade)
- [x] `app/scripts/seed.py` idempotent (ON CONFLICT): user `admin` (password_hash placeholder — auth chưa enforce) + gateway `GW_S7200_01` + slave addr 1
- [x] `/api/v1/health` thật: pg (`SELECT 1` asyncpg), influx (`GET /health`), redis (`PING`), mqtt (TCP connect qua `app/ingestion/mqtt_client.tcp_check`) → `{"status":"ok|degraded","checks":{...}}`, 200/503
- [x] `stores/{postgres,influx,redis_client}.py` — helper kết nối dùng chung cho M3+
- [x] `.env` local sinh secrets ngẫu nhiên bằng openssl (không commit); `.env.example` cập nhật
- [x] IP:port EMQX công bố cho team firmware: **`192.168.1.3:1883`** (máy chạy compose, cùng lớp mạng với gateway 192.168.1.x) — bàn giao khi cập nhật firmware theo Q1

## 3. Kết quả kiểm chứng DoD

| Tiêu chí DoD | Lệnh / cách kiểm tra | Kết quả thực tế | Đạt? |
|---|---|---|---|
| `docker compose up -d` → 7 service healthy/running | `docker compose ps` | backend/emqx/influxdb/nginx/postgres/redis `(healthy)`, frontend `Up` | ☑ |
| `curl .../health` ok + 4 store connected | `curl http://localhost/api/v1/health` (qua nginx) | `{"status":"ok","checks":{"postgres":true,"influxdb":true,"redis":true,"mqtt":true}}` | ☑ |
| Subscribe `devices/+/+` không lỗi | `docker run eclipse-mosquitto mosquitto_sub -h emqx ...` + pub probe | nhận `{"probe":1}`, exit 0 | ☑ |
| EMQX dashboard port 18083 | `curl -w %{http_code} localhost:18083` | `200` | ☑ |
| Bảng pg đúng DDL | `psql \dt` | `gateways, slaves, signal_defs, gateway_events, users, alembic_version` | ☑ |
| IP broker gửi firmware | `ip -4 addr` | `192.168.1.3:1883` — ghi tại §2 báo cáo này | ☑ |
| (extra) pytest + ruff + black | `backend$ pytest -q` | `3 passed` (thêm test shape /health), lint sạch | ☑ |
| (extra) seed idempotent | rebuild backend → command chạy lại seed | lần 2 không lỗi, không trùng dòng | ☑ |

## 4. Phát hiện mới so với kế hoạch

1. **Bug Dockerfile (sửa trong milestone này):** `COPY alembic.ini alembic ./` làm *flatten* thư mục `alembic/` vào `/srv` → `alembic upgrade head` fail "Path doesn't exist". Sửa thành 2 dòng `COPY alembic.ini ./` + `COPY alembic ./alembic`.
2. **Bug `postgres.check()`:** gọi `sqlalchemy.ext.asyncio.text()` (không tồn tại) — exception bị nuốt nên health trả `postgres:false` dù DB sống. Sửa: `import sqlalchemy as sa; sa.text(...)`. Bài học: check lỗi im lặng → M2+ các check/store nên log warning khi exception, không return False trần.
3. Image `emqx:5` không có sẵn `mosquitto_sub/pub` — test broker dùng container `eclipse-mosquitto:2` attach network `signalbridge_default` (đã verify roundtrip).
4. Snippet compose trong plan §5.2 là bản rút gọn (thiếu healthcheck influx/nginx, dòng DATABASE_URL viết tắt không hợp lệ YAML) — file `docker-compose.yml` thực tế là nguồn chuẩn, plan không đổi (chi tiết implementation).
5. `hostname -I` không có trên môi trường shell dev (Arch minimal) → dùng `ip -4 addr`.

## 5. Tồn đọng & rủi ro phát sinh

| Mục | Chi tiết | Xử lý ở đâu |
|---|---|---|
| Ports DB/broker expose ra LAN (5432/8086/6379/1883) | Tiện dev nhưng rủi ro nếu máy nối mạng xưởng — gateway firmware cần 1883 mở, các port kia nên bind 127.0.0.1 hoặc bỏ khi prod | Quyết định trước khi deploy thật (chỉnh compose, không đổi code) |
| MQTT chưa có auth/ACL | Phase 1 theo plan (broker LAN trust) | Backlog auth |
| Emqx dashboard password | Đã sinh trong `.env` local | Giữ bí mật |

## 6. Câu hỏi cần team hardware/firmware trả lời

Không phát sinh mới. Nhắc lại bàn giao Q1: **firmware đổi broker sang `192.168.1.3:1883`**.

## 7. Ảnh hưởng tới tài liệu

- [x] Cập nhật `REPORT_OVERVIEW.md` (M1 ✅, 2/9, nhật ký)
- [x] `PROJECT_PLAN.md` giữ v1.3 — không đổi thiết kế
- [x] `README.md` cập nhật lệnh chạy compose
