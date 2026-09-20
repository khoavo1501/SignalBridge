# REPORT_OVERVIEW — Báo cáo tổng quan & tiến trình dự án

> **File này là điểm vào đầu tiên cho mọi phiên làm việc và mọi lần đọc prompt.**
> Cập nhật TRONG LẦN COMMIT của mỗi phase/chức năng hoàn thành. Không để lịch sử cũ bị mất — chỉ thêm/cập nhật trạng thái.
> Quy ước chi tiết: `PROJECT_PLAN.md` §6. Nguồn chân lý payload: `docs/payloads/`.

- **Dự án:** SignalBridge — giám sát PLC realtime
- **Plan:** `PROJECT_PLAN.md` v1.3 (2026-09-19)
- **Cập nhật gần nhất:** 2026-09-20 — M8 hoàn thành (Admin UI CRUD gateway + gộp backlog `/history` newest-kept + `/events` aggregate, xem [M8-admin-ui.md](M8-admin-ui.md)) — **hết 9/9 milestone phase 1**

## Trạng thái tổng thể

**Phase hiện tại:** cả 9 milestone M0–M8 hoàn thành. Phần còn lại là **backlog sau M8** (plan §7): auth JWT thật, rules engine cảnh báo, alerting email/SMS, toàn màn hình xưởng, multi-user prefs; cộng bundle frontend 603 kB và 2 câu hỏi hardware Q2b/Q7.
**Tổng tiến độ:** 9/9 milestone.

| Milestone | Phạm vi chức năng | Trạng thái | Báo cáo chi tiết |
|---|---|---|---|
| M0 | Scaffolding repo & tài liệu nền tảng | ✅ Done (2026-09-19) | [M0-scaffolding.md](M0-scaffolding.md) |
| M1 | Hạ tầng Docker (7 service) | ✅ Done (2026-09-19) | [M1-docker-infra.md](M1-docker-infra.md) |
| M2 | Kết nối MQTT & xác nhận payload | ✅ Done (2026-09-19) | [M2-mqtt-ingestion.md](M2-mqtt-ingestion.md) |
| M3 | Persist Influx/Postgres/Redis | ✅ Done (2026-09-19) | [M3-persistence.md](M3-persistence.md) |
| M4 | REST API đọc dữ liệu | ✅ Done (2026-09-19) | [M4-rest-api.md](M4-rest-api.md) |
| M5 | WebSocket realtime | ✅ Done (2026-09-19) | [M5-websocket-realtime.md](M5-websocket-realtime.md) |
| M6 | Frontend dashboard tổng quan (+ M6b redesign 5 trang theo tham chiếu admin IIoT) | ✅ Done (2026-09-19) | [M6-frontend-dashboard.md](M6-frontend-dashboard.md) |
| M7 | Frontend chi tiết gateway/slave | ✅ Done (2026-09-20) | [M7-frontend-detail.md](M7-frontend-detail.md) |
| M8 | Admin UI đăng ký & quản lý gateway (Q8) + backlog gộp (`/history` newest-kept, `/api/v1/events` aggregate) | ✅ Done (2026-09-20) | [M8-admin-ui.md](M8-admin-ui.md) |

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
| 2026-09-19 | **WS telemetry throttle = aggregate latest-wins + trailing flush đúng boundary** (không phải gate-drop — gate-drop bị quantize theo input: 100 ms input + 250 ms gate → 300 ms thực tế, fail DoD ±10%) | M5 report §4, PROJECT_PLAN §4.2 |
| 2026-09-19 | **Badge M6 tính phía client bằng tick 1 s** (`badgeOf = broker state × độ tươi telemetry`) — server không gửi frame mỗi giây nên transition online→stale phải do UI tự recompute; đạt "≤ ngưỡng + 1 nhịp UI" | M6 report §4, ràng buộc #5 |
| 2026-09-19 | **M6b: một socket WS dùng chung mọi route** (LiveProvider bọc BrowserRouter, không phải per-page) — tránh N socket khi điều hướng SPA; verify `ws_clients` ổn định qua 5 reload | M6 report §2/§3 |
| 2026-09-20 | **M7: chart slave dùng trục thời gian hợp nhất** (rows = union mọi mốc của mọi signal đang chọn + WS tail; signal vắng tại mốc → null → Line `connectNulls=false` đứt đoạn) — gap hc0 hiển thị đúng, không crash; hệ quả: khoảng im lặng hoàn toàn chỉ thấy đứt khi có signal khác phủ cùng khoảng (M7 report §4.3) | M7 report §2/§4 |
| 2026-09-20 | **M7: `lastSeen` của badge slave = max(REST /latest, mốc WS tail cuối)** — REST refresh 15 s > ngưỡng stale 10 s nên không được tính độ tươi chỉ từ /latest | M7 report §4.4 |
| 2026-09-20 | **M8: `/history` flux đổi tail `sort desc → limit → sort asc`** — khi vượt cap giữ điểm **MỚI NHẤT** (cả raw lẫn agg), thay vì cũ nhất làm chart realtime mất đuôi (fix backlog M7 §5.1) | M8 report §2/§3, M7 report §4.1 |
| 2026-09-20 | **M8: `GET /api/v1/events` aggregate toàn hệ thống** (join gateways, con trỏ `before`+`code`, limit clamp 500) — EventsPage dùng 1 request thay loop theo gateway (backlog M7 §5.2) | M8 report §2 |
| 2026-09-20 | **M8: `DELETE /gateways/{id}` dọn Redis theo scan `sb:latest:{gw}:*`** — không tin mỗi bảng slaves (gateway có telemetry nhưng chưa có slave row sẽ leak key); Influx **giữ nguyên** theo Q5 | M8 report §4.1 |
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
| 2026-09-19 | **M2 ✅** — parser adapter `s7200_v1` + registry, aiomqtt listener có backoff, `gateway_simulator` phát lại đủ 5 payload, E2E 206/206 msg khớp ground truth (8 DI + di_word + ai_raw, vắng hc0/c0 đúng firmware), LWT offline ~3 s. 18 unit test |
| 2026-09-19 | **M3 ✅** — influx_writer batch 1 s (telemetry+diag, sparse, server-time), redis writer 3 key §3.3, pg writer (info upsert, events, STATUS dedupe qua Redis). DoD đủ 5 mục trên stack thật: 10 điểm/s steady ±0%, kill -9 backend → retain replay 0 event trùng, mỗi kill/restart đúng 2 dòng STATUS. Bug sửa: `Point.add_field`→`field`; `:raw::jsonb`→`CAST(:raw AS jsonb)`. 28 unit test |
| 2026-09-19 | **M4 ✅** — 7 endpoint đọc (§4.1) + error contract + badge 3 trạng thái. DoD live: stale khi telemetry dừng (MQTT vẫn online), offline < 5 s sau LWT, health 503 khi redis chết, coverage API 98%, 49 test. Bug: Influx 2.7 không có `typeof()` → agg tách 2 flux numeric/DI merge Python; sửa M3 sót meta info (fw/hw/ip/mac) trong upsert. POST/DELETE gateways hoãn sang M8 |
| 2026-09-19 | **M5 ✅** — WS hub + subscribe §4.2, snapshot 5 ms, đủ 5 kind frame (info sau upsert, diag/event ngay), heartbeat uvicorn ping 30 s, Broadcaster Local/RedisPubSub (env `WS_PUBSUB_ENABLED`), stats `ws_clients/published/dropped`. DoD live: 41 frame/10 s nhịp đúng 250 ms (+2,5%), status offline tới client 3,0 s sau kill -9, reconnect sau restart backend, CPU không tăng quá noise. **Quyết định kỹ thuật: throttle = latest-wins + trailing flush boundary** (gate-drop thuần bị quantize theo input 100 ms → 300 ms, fail ±10%). 69 test |
| 2026-09-19 | **M6 ✅** — dashboard tổng quan: `api/client.ts` + `useGatewaySocket` (backoff 1→30 s), `StatusBadge` 3 trạng thái tooltip Việt, `GatewayCard` nhãn "(raw)" (Q2), `SummaryPage` REST nền + WS snapshot/frames đè, tick 1 s recompute badge (ràng buộc #5). DoD live qua nginx: ai_raw đổi liên tục nhịp 250 ms, stale hiển thị ngay khi status online + telemetry dừng, offline ~0,5 s sau kill -9, `ws_clients` 1→3→1 không leak, reconnect sau restart backend, build TS strict sạch, 69 test backend không đổi |
| 2026-09-19 | **M6b ✅ redesign** theo 5 screenshot tham chiếu admin IIoT (user yêu cầu, skills design-taste-frontend + redesign-existing-projects): dark tokens (nền #0c0e12, amber #dfa24a đơn accent, mono cho số), topbar + sidebar, 5 route `/` `/events` `/diagnostics` `/gateways/:id` `/gateways/:id/slaves/:addr` — KPI row, card sparkline (seed /history + stream WS), badge per-slave, chart Recharts 15m/1h/6h/24h, Events filter severity/device/code + phân trang, Diagnostics + history từ frame. Verify lại kết nối backend qua nginx: đủ 3 nhịp badge online→stale→offline→online trên UI mới không reload, filter 36→23 dòng, không leak WS (socket dùng chung). Fix phát sinh: auto-refresh REST 5 s cho GatewayDetail (badge per-slave kẹt stale), `.badge` nowrap. Phạm vi M7 cover phần lớn — chốt phần còn lại trước khi bắt đầu |
| 2026-09-19 | **Tài liệu hạ tầng** — [INFRA-ports-va-tai-khoan.md](INFRA-ports-va-tai-khoan.md): bảng cổng (public + nội bộ docker network), tài khoản truy cập từng hệ thống (không ghi secrets — trỏ biến trong `.env`), việc mở cho production (bind 127.0.0.1, MQTT ACL, Redis password, AUTH_ENABLED) |
| 2026-09-20 | **M7 ✅** — drill-down slave realtime: `subscribeTelemetry` pub-sub trong LiveContext, SlaveDetailPage viết lại (4 khoảng thời gian, pills signal, trục hợp nhất + gap null, WS tail 250 ms), Events phân trang sâu bằng con trỏ `before`, cột seq gap 1h ước lượng (R1) ở Chẩn đoán, trang 404. DoD live: ai_raw 1h 0,105 s/3066 điểm khớp influx CLI 3136 (lệch mép cửa sổ), events 81=81 khớp psql, gap hc0 đứt đoạn không crash (6119 điểm · 4125 mốc trống), 404/503 influx error-box không white-screen. **Phát hiện: `/history` raw flux `sort asc + limit` giữ điểm CŨ NHẤT — sim 100 ms đã chạm cap 5000 (5.031 điểm/h); workaround frontend `limit=20000`, fix gốc backend vào backlog M8.** 2 fix UI: badge trễ giả (lastSeen=max REST,WS), truncation. Build TS strict sạch |
| 2026-09-20 | **M8 ✅ — hoàn thành 9/9 milestone phase 1.** Admin UI `/admin` (GatewaysAdminPage): CRUD gateway không đụng SQL — POST validate id/adapter (400/409/422), PATCH inline display_name + enable/disable, DELETE confirm (PG cascade + Redis scan `sb:latest:{gw}:*`, Influx giữ theo Q5), panel "chưa đăng ký" từ `pipeline._unknown_seen` + quick-add, GW_S7200_02 (simulator instance 2) lên dashboard badge online; E2E qua UI đủ mọi mục DoD gồm 409 thân thiện không white-screen. **Gộp backlog được duyệt:** fix `/history` tail `sort desc→limit→sort asc` (vượt cap giữ điểm MỚI NHẤT — verify last=05:29:55 sát mép stop) + `GET /api/v1/events` aggregate (EventsPage còn 1 request, cursor `next_before` toàn cục). Phát hiện E2E: leak latest-key của slave chưa có row → sửa scan. 83 test backend (+14 M8), ruff/black/eslint/prettier/build sạch. Còn lại: backlog sau M8 (auth JWT thật là chính) + Q2b/Q7 mở |
