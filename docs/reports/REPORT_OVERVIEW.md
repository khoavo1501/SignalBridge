# REPORT_OVERVIEW — Báo cáo tổng quan & tiến trình dự án

> **File này là điểm vào đầu tiên cho mọi phiên làm việc và mọi lần đọc prompt.**
> Cập nhật TRONG LẦN COMMIT của mỗi phase/chức năng hoàn thành. Không để lịch sử cũ bị mất — chỉ thêm/cập nhật trạng thái.
> Quy ước chi tiết: `PROJECT_PLAN.md` §6. Nguồn chân lý payload: `docs/payloads/`.

- **Dự án:** SignalBridge — giám sát PLC realtime
- **Plan:** `PROJECT_PLAN.md` v1.3 (2026-09-19)
- **Cập nhật gần nhất:** 2026-09-19 — M1 hoàn thành (compose + schema + seed + health, xem [M1-docker-infra.md](M1-docker-infra.md))

## Trạng thái tổng thể

**Phase hiện tại:** M1 hoàn thành — tiếp theo M2 (MQTT ingestion + parser).
**Tổng tiến độ:** 2/9 milestone.

| Milestone | Phạm vi chức năng | Trạng thái | Báo cáo chi tiết |
|---|---|---|---|
| M0 | Scaffolding repo & tài liệu nền tảng | ✅ Done (2026-09-19) | [M0-scaffolding.md](M0-scaffolding.md) |
| M1 | Hạ tầng Docker (7 service) | ✅ Done (2026-09-19) | [M1-docker-infra.md](M1-docker-infra.md) |
| M2 | Kết nối MQTT & xác nhận payload | ⚪ Pending | — |
| M3 | Persist Influx/Postgres/Redis | ⚪ Pending | — |
| M4 | REST API đọc dữ liệu | ⚪ Pending | — |
| M5 | WebSocket realtime | ⚪ Pending | — |
| M6 | Frontend dashboard tổng quan | ⚪ Pending | — |
| M7 | Frontend chi tiết gateway/slave | ⚪ Pending | — |
| M8 | Admin UI đăng ký & quản lý gateway (Q8) | ⚪ Pending | — |

Ký hiệu: ⚪ Pending · 🔵 In progress · 🟡 Blocked · ✅ Done

## Các quyết định đã chốt

| Ngày | Quyết định | Nguồn |
|---|---|---|
| 2026-09-19 | Stack cố định: FastAPI monolith + React/Vite + PG/Influx/EMQX/Redis/Nginx/Docker | PROJECT_PLAN.md header |
| 2026-09-19 | **Q1:** EMQX deploy trên máy chủ mới + firmware đổi IP broker (không thay Mosquitto tại 192.168.1.4) | PROJECT_PLAN.md §1.3 |
| 2026-09-19 | **Q2 (tạm):** hiển thị giá trị analog dạng raw — `value=raw, scaled=false, unit=null`, nhãn "(raw)"; KHÔNG đoán hệ số scale. Công thức thật vẫn chờ team hardware | PROJECT_PLAN.md §4.1, §8 |
| 2026-09-19 | **Q3:** chấp nhận `hc0`/`c0` vắng mặt (firmware chưa poll region 54–58), parser xử lý thiếu field, không chờ firmware | PROJECT_PLAN.md §8 |
| 2026-09-19 | **Q4:** các gateway cùng loại payload → dùng lại adapter `s7200_v1`; adapter pattern vẫn giữ cho loại khác tương lai | PROJECT_PLAN.md §2, §8 |
| 2026-09-19 | **Q5:** retention InfluxDB **60 ngày** | PROJECT_PLAN.md §3.2 |
| 2026-09-19 | **Q6:** demo giữ ngưỡng stale 10 s (env `STALE_THRESHOLD_S`), điều chỉnh sau nếu cần | PROJECT_PLAN.md §3.3 |
| 2026-09-19 | **Q8:** đăng ký gateway mới qua **UI admin** → thêm gateway CRUD (`POST/PATCH/DELETE /api/v1/gateways`) + milestone **M8** | PROJECT_PLAN.md §4.1, §7 |
| 2026-09-19 | Timestamp chuẩn = server receive time, bỏ `ts` payload (luôn = 0) | ràng buộc #1 |
| 2026-09-19 | Parser theo adapter pattern; payload gateway loại mới phải lưu vào `docs/payloads/` trước khi viết adapter | PROJECT_PLAN.md §2, §6 |

## Câu hỏi mở còn lại

| # | Câu hỏi | Trạng thái | Chặn gì |
|---|---|---|---|
| Q2b | Công thức scale cuối cùng cho `ai_raw`/`hc0`/`c0` (a/b hoặc lookup, dải AIW0) | ⏳ Chờ team hardware — demo chạy raw, không chặn | Hiển thị đơn vị thật về sau |
| Q7 | `diag.tx_packets`/`tx_failures` (semantics sai) — gắn nhãn gì hay ẩn? | ⏳ Chưa trả lời — tạm hiển thị kèm chú thích "biến đếm Modbus" | Không chặn |

## Rủi ro đang theo dõi

- R1: Telemetry QoS 0 mất gói không phát hiện đầy đủ — gap `seq` chỉ ước lượng (chấp nhận phase 1).
- R2: `reset_reason` firmware cứng "POWER_ON" — không dùng làm tín hiệu restart, suy từ chuỗi STATUS events.

## Nhật ký cập nhật

| Ngày | Sự kiện |
|---|---|
| 2026-09-19 | Lập PROJECT_PLAN.md v1.0; chốt Q1, Q2 → v1.1 |
| 2026-09-19 | Khởi tạo hệ thống quản lý docs: REPORT_OVERVIEW.md, template báo cáo, AGENTS.md (quy tắc đọc docs trước khi làm bất kỳ việc gì) |
| 2026-09-19 | Người dùng trả lời Q3–Q6, Q8 → plan v1.3: retention 60d, adapter s7200_v1 dùng chung cho các gateway cùng loại, ngưỡng stale 10 s, thêm gateway CRUD + milestone M8 (Admin UI). Chỉ còn Q7 (+ công thức scale Q2b) mở |
| 2026-09-19 | **M0 ✅** — scaffold backend/frontend, tooling, Dockerfiles, CI workflow. pytest/ruff/black/eslint/prettier/vite build/docker build đều xanh thủ công (chưa verify CI trên remote). Phát hiện: pin phải resolve lại cho Python 3.14; npm cục bộ chặn postinstall esbuild. **Lưu ý bảo mật: nhiều prompt injection giả "[System Instructions]" (gồm lệnh `rm -rf ~/.qoder`) trong phiên M0 — tất cả bị từ chối, chi tiết §8 báo cáo M0** |
| 2026-09-19 | **M1 ✅** — compose 7 service healthy, `/api/v1/health` ok (pg+influx+redis+mqtt), schema baseline + seed chạy qua container, MQTT roundtrip verified. **Bàn giao Q1: broker EMQX = `192.168.1.3:1883` cho firmware.** Bug sửa trong milestone: flatten `COPY alembic` trong Dockerfile; `sa_async.text` sai module. Injection tiếp tục xuất hiện — vẫn bị từ chối toàn bộ |
