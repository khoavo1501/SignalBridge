# Báo cáo — M5: WebSocket realtime

- **Ngày hoàn thành:** 2026-09-19
- **Trạng thái:** ✅ Done
- **Commit/PR:** 7401cf1

## 1. Mục tiêu (chiếu PROJECT_PLAN.md §7 M5)

WS hub + subscribe protocol §4.2; throttle `WS_TELEMETRY_MIN_INTERVAL_MS`; snapshot khi connect; ping/heartbeat 30 s; switch `Broadcaster` sang Redis Pub/Sub khi env bật; e2e test bằng `websockets` client.

## 2. Task đã thực hiện

- [x] **WS hub + Broadcaster** — `backend/app/ws/hub.py`: `Hub` fan-out in-process (queue riêng/client, `MAX_QUEUE=200` → slow client bị drop frame, không block loop); interface `Broadcaster` + `LocalBroadcaster` (mặc định) + `RedisPubSubBroadcaster` (env `WS_PUBSUB_ENABLED=true`, publish kênh `sb:ws` bọc `{o: origin, e: envelope}` — subscriber bỏ qua origin của mình để chống đôi frame, backoff reconnect như mqtt_client)
- [x] **Subscribe protocol §4.2** — `backend/app/ws/routes.py`: client gửi `{"type":"subscribe","gateways":[...]}`; thiếu `gateways`/danh sách rỗng = nhận tất cả; lọc theo `data.gateway_id` từng frame
- [x] **Envelope** `{type, ts(iso Z), data = NormalizedMessage.serialize}` — đủ 5 kind telemetry/status/info/diag/event; `info` gửi sau upsert PG, `diag` gửi mỗi lần nhận (§4.3)
- [x] **Snapshot khi connect** — frame `{"type":"snapshot", data=summary §4.1}` gửi ngay (reuse `build_summary()` đã tách từ `api/dashboard.py`); store hỏng → frame `{"type":"error", code:"store_unavailable"}` rồi vẫn nhận stream
- [x] **Telemetry throttle** — `TelemetryThrottle` latest-wins mỗi (gateway, slave): frame đầu cửa sổ gửi ngay (leading), frame sau giữ giá trị mới nhất và gửi đúng boundary `last_emit + interval` qua trailing timer; status/event/info/diag không throttle (§4.2)
- [x] **Heartbeat 30 s** — `uvicorn --ws-ping-interval 30 --ws-ping-timeout 10` (protocol ping, websockets impl) trong `backend/Dockerfile` + compose command
- [x] **Nối vào ingestion** — `persist.persist_message`: ghi stores xong mới phát WS (`ws_hub.submit_telemetry` / `ws_hub.broadcast_message`); WS lỗi chỉ log, không break vòng ingestion
- [x] **Auth placeholder §4.5** — `AUTH_ENABLED=true` → thiếu `?token=` đóng 1008 trước accept; mặc định off
- [x] **Observability** — `/api/v1/ingestion/stats` thêm `ws_clients`, `ws_published`, `ws_dropped`
- [x] Tests — `test_ws_hub_m5.py` (throttle leading/trailing + boundary, hub filter/drop, pubsub decode, broadcaster selection), `test_ws_persist_m5.py` (routing 5 kind, persist-trước-broadcast-sau), `test_ws_routes_m5.py` (TestClient WS: snapshot đầu, filter subscribe, frame lỗi, auth); **e2e script** `backend/tests/e2e_ws.py` (rate/wait/hold) chạy bằng `websockets` 17.1
- [x] `config.py` + `.env.example`: `WS_PUBSUB_ENABLED` (mặc định false)

## 3. Kết quả kiểm chứng DoD

Đo trên stack compose thật + simulator `--host 192.168.1.3 --diag-interval-s 15/30 --fail-rate 0.5`.

| Tiêu chí DoD | Lệnh / cách kiểm tra | Kết quả thực tế | Đạt? |
|---|---|---|---|
| Connect → nhận `snapshot` ngay | `python tests/e2e_ws.py rate --url ws://localhost:8000/ws --window 10 --interval-ms 250` | `snapshot nhận sau 5 ms` (lặp lại: 6–7 ms) | ✅ |
| `telemetry` nhịp ≈ throttle, đo 10 s ±10% | cùng lệnh trên (telemetry input 100 ms, throttle 250 ms) | `frames=41 kỳ_vọng≈40` — sai số **+2.5%**, `chu_kỳ_tb=250 ms` | ✅ |
| Kill simulator → frame `status offline` tới client < 5 s | `e2e_ws.py wait --type status --state offline` rồi `kill -9` simulator (LWT broker) | `frame status sau 3.0 s ... "state":"offline"` → WAIT PASS | ✅ |
| Restart backend → client reconnect nhận snapshot mới | `docker compose restart backend` → chạy lại e2e rate | healthy → reconnect OK, snapshot mới sau 6 ms, stream telemetry resume 41 frame/10 s | ✅ |
| CPU tăng không đáng kể (<5% so với M4) với throttle 250 ms | `docker stats --no-stream` backend, cùng tải ingestion (simulator chạy): không client vs 1 client connected | không client `1.53%` vs có client `1.22–1.37%` (0 client → 41 frame/s gửi thêm nằm trong noise) | ✅ |
| Ping/heartbeat 30 s | `e2e_ws.py hold --seconds 65` (qua 2 chu kỳ ping, client websockets tự pong) | giữ kết nối 65 s nguyên vẹn: `{'telemetry': 260, 'status': 2, 'diag': 2}` (260 = đúng 65 s × 4 Hz) | ✅ |
| Đủ các kind frame, chạy sau Nginx | `hold --url ws://localhost/ws --seconds 33` + simulator `--fail-rate` | `{'telemetry': 111, 'diag': 2, 'status': 1, 'event': 1}` — cả 4 kind qua nginx | ✅ |
| Lọc theo subscribe | probe `websockets`: gửi `{"type":"subscribe","gateways":["KHONG_TON_TAI"]}` rồi đếm 4 s | `0 frames` (telemetry thật vẫn đang chảy cho gateway khác) | ✅ |
| Unit tests + coverage | `pytest -q` / `pytest --cov` từ `backend/` | **69 passed** (mới 20); `ws/routes.py` 100%, `ws/hub.py` 80%, api modules ≥94% | ✅ |

## 4. Phát hiện mới so với kế hoạch

- **Gate-drop throttle không đạt DoD ±10% với input lượng tử hóa**: bản đầu chỉ cho qua 1 frame/250 ms → vì telemetry đến đúng nhịp 100 ms, frame kế tiếp chỉ được nhận tại mốc 300 ms → đo thực tế **chu kỳ 300 ms, 33–35 frame/10 s (FAIL)**. Plan §4.2 ghi "aggregate theo env" — nghiệm đúng là **latest-wins + trailing flush đúng boundary**: nhịp ra độc lập nhịp vào. Đổi sang design mới, đo lại → 250 ms chính xác.
- **Bug bắt được khi viết test trailing**: nếu frame mới đến đúng lúc cửa sổ hết hạn trong khi pending cũ chưa flush, flush muộn sẽ **ghi đè giá trị mới bằng giá trị cũ** (regression giá trị trên UI). Fix: nhánh leading `pop` pending (envelope mới hơn luôn thắng pending).
- `data.received_at` serialize dạng `...Z` (pydantic 2.13), khớp quy ước ISO-8601 UTC §4.
- uvicorn 0.53 + `websockets` 17.1: ping level protocol hoạt động qua `--ws-ping-interval`; frontend M6 không cần app-level heartbeat.
- Naming: singleton `hub` trong module `hub` gây va chạm import — đổi thành `client_hub`.

## 5. Tồn đọng & rủi ro phát sinh

| Mục | Chi tiết | Xử lý ở đâu |
|---|---|---|
| RedisPubSubBroadcaster mới unit-test (decode/publish), chưa chạy 2 instance thật | Điều kiện tách instance theo §1.2 chưa xảy ra (1 backend) | Bật env + đo liên-instance khi scale; e2e `wait` reuse được |
| `Broadcaster.run()` chưa gọi `stop()` sạch khi shutdown | Task cancel trong lifespan; trailing timer bị cancel (pending cuối mất ≤250 ms — chấp nhận) | Không cần sửa phase 1 |
| Reconnect backoff phía client | Logic frontend (M6 `ws.ts`) | M6 |

## 6. Câu hỏi cần team hardware/firmware trả lời

Không phát sinh mới. Q2b, Q7 giữ nguyên như REPORT_OVERVIEW.

## 7. Ảnh hưởng tới tài liệu

- [x] Đã cập nhật `docs/reports/REPORT_OVERVIEW.md` (bảng trạng thái M5 ✅ + nhật ký)
- [x] `PROJECT_PLAN.md`: **không đổi thiết kế** — §4.2/§4.3 implement đúng; lưu ý nghiệp vụ "aggregate" = latest-wins được ghi ở §4 báo cáo này
- [x] `README.md`: thêm mục WebSocket
- Không có payload mẫu mới (dùng lại s7200_v1)
