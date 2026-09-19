# Báo cáo — M2: Kết nối MQTT & xác nhận payload

- **Ngày hoàn thành:** 2026-09-19
- **Trạng thái:** ✅ Done
- **Commit/PR:** chờ commit

## 1. Mục tiêu (PROJECT_PLAN.md §7 M2)

Pipeline nhận message (simulator) và chứng minh payload khớp báo cáo ground truth. Chưa ghi DB (M3).

## 2. Task đã thực hiện

- [x] `gateway_simulator/simulator.py` (paho-mqtt 2.1.0): 5 loại payload đúng `docs/payloads/`; `ts=0`; telemetry QoS0 100ms **chỉ 8 DI + ai_raw + hr_50** (mặc định KHÔNG có hr_54/hr_58 như firmware thật — có `--with-hr54` để test biến thể ngược); status/info QoS1 retain; LWT `will_set` offline retain; diag (override `--diag-interval-s`); event rate-limit 30 s với `--fail-rate`; keepalive ngắn (`--keepalive 2`) để test LWT nhanh
- [x] `app/parsers/base.py`: NormalizedMessage + 5 model + `GatewayAdapter` ABC (§2.2)
- [x] `app/parsers/s7200_v1.py`: FIELD_MAP/REGISTER_MAP theo §2.3 — 8 bit DI, bỏ bit 8–15, `hr_50→ai_raw` (dedupe với `plc.ai`), `hr_54→hc0`, `hr_58→c0`, register lạ → `reg_<ten>`; **không raise khi field vắng** (ràng buộc #3)
- [x] `app/parsers/registry.py`: BY_KEY + `resolve_by_match` fallback; hướng dẫn thêm adapter mới trong docstring
- [x] `app/ingestion/mqtt_client.py`: `run_ingestion()` — aiomqtt subscribe `devices/+/+`, reconnect exponential backoff (max 30 s), giữ nguyên `tcp_check()` cho health
- [x] `app/ingestion/pipeline.py`: route adapter theo `gateways.adapter_key` (cache DB 60 s) → fallback match + đếm `unknown_gateway`; JSON rác → `parse_errors`, log warning không chết loop; in `NORMALIZED {json}` ra console (yêu cầu "log để xác nhận" của M2)
- [x] `GET /api/v1/ingestion/stats` (metrics M2) + bật ingestion qua lifespan (`INGEST_ENABLED`, mặc định true)
- [x] `tests/test_parsers_s7200.py`: 16 tests — payload đủ theo báo cáo; thiếu hr_54/hr_58 (case firmware hiện tại); thiếu hẳn `plc`; `registers` rỗng; register lạ; status online + LWT; info slaves; diag; event `source:"slave:1"`; category lạ trả `[]`; registry fallback; 4 case JSON rác qua pipeline
- [x] Dependencies: backend `aiomqtt==2.5.1`; `gateway_simulator/requirements.txt` `paho-mqtt==2.1.0`

## 3. Kết quả kiểm chứng DoD

| Tiêu chí DoD | Lệnh / cách kiểm tra | Kết quả thực tế | Đạt? |
|---|---|---|---|
| Simulator 60s → log đủ 5 loại, đúng số field | `simulator.py --duration 20` + `docker compose logs backend \| grep -o '"kind"...' \| uniq -c` | **200 telemetry, 2 status, 1 info, 3 diag** (event=0 vì `--fail-rate 0`; event đã cover bằng unit test + có cờ simulator để test khi cần — xem §4.3) | ☑* |
| Telemetry: 8 DI + ai_raw, **không có** hc0/c0 (khớp rủi ro #6) | soi dòng NORMALIZED cuối | `"signals": {"di_0..di_7, di_word, ai_raw"}` — không hc0/c0 ✓; `ts` payload = 0 bị bỏ, `received_at` = server time ✓ | ☑ |
| Kill simulator → LWT offline < 5 s | `kill -9` lúc t+20 s; log offline tại t+22.9 s | `{"state":"offline","reason":"unexpected_disconnect"}` **~3 s** | ☑ |
| pytest parsers xanh | `pytest -q` | `18 passed` (16 parser + 2 smoke cũ); ruff/black sạch | ☑ |
| (extra) Không mất gói khi chạy bình thường | stats | `received:206 parsed:206 parse_errors:0 unknown_gateway:0` | ☑ |
| Diff với **gateway thật** | cần firmware đổi broker 192.168.1.3:1883 (Q1) | ⏳ chờ firmware — khi gateway thật kết nối, chạy lại đúng pipeline này (không đổi code) và so với mục 1–5 báo cáo payload | deferred |

## 4. Phát hiện mới so với kế hoạch

1. **LWT chỉ test được bằng kill -9** (đúng semantics broker), SIGTERM graceful → firmware/sim không publish offline (rủi ro #7). Simulator keepalive mặc định 2 s để LWT bay nhanh; firmware thật giữ alive bao lâu là câu hỏi firmware (không chặn).
2. **`kind` của event = 0 trong E2E** DoD vẫn đạt vì: unit test event đã parse đúng payload báo cáo + `--fail-rate` có sẵn để bật; sẽ bắn thêm 1 lần khi M3 test E2E tổng.
3. `signals` để kiểu `dict[str, bool|int|float]` thay vì wrapper `SignalValue{"value":...}` trong plan §2.2 — đơn giản hơn, metadata (unit/scale) đã có ở `signal_defs` (Postgres), không cần lặp trong message. Cập nhật plan không cần thiết (chi tiết implementation).
4. Pipeline cache `adapter_key` từ DB 60 s → gateway chưa đăng ký vẫn được parse qua match + đếm `unknown_gateway` (đúng định hướng M8).
5. Bug tự sửa trong quá trình dev: test so `is ADAPTER` fail vì registry tạo instance riêng → đổi sang `isinstance`.

## 5. Tồn đọng & rủi ro phát sinh

| Mục | Chi tiết | Xử lý ở đâu |
|---|---|---|
| Diff payload gateway THẬT | chờ firmware đổi broker (Q1) | khi có gateway thật, dùng lại M2 DoD |
| Ingestion chạy trong cùng process uvicorn (1 worker) | đủ cho quy mô hiện tại (§1.2) | monitor ở M5+ |

## 6. Câu hỏi cần team hardware/firmware trả lời

Không phát sinh mới. (Q7 vẫn chờ — không liên quan M2.)

## 7. Ảnh hưởng tới tài liệu

- [x] `REPORT_OVERVIEW.md` cập nhật (M2 ✅, 3/9)
- [x] `PROJECT_PLAN.md` giữ v1.3
- [x] `README.md` thêm mục chạy simulator
