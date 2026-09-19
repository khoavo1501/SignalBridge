# Báo cáo — M4: REST API đọc dữ liệu

- **Ngày hoàn thành:** 2026-09-19
- **Trạng thái:** ✅ Done
- **Commit/PR:** chờ commit

## 1. Mục tiêu (PROJECT_PLAN.md §7 M4)

Toàn bộ endpoint đọc §4.1 hoạt động với dữ liệu thật từ 3 kho (M3), tính badge 3 trạng thái theo §3.3, lỗi theo contract `{"error":{code,message}}`.

## 2. File đã tạo/sửa

- [x] `backend/app/api/common.py` (mới): `iso_z`, `compute_badge` (§3.3), `require_gateway`/`require_slave` (404 riêng theo param — §4.4), `parse_iso`
- [x] `backend/app/api/errors.py` (mới): `ApiError` + handler bao `RequestValidationError` → shape `{"error":{code,message}}`
- [x] `backend/app/api/dashboard.py` (mới): `GET /dashboard/summary` — badge online/stale/offline, `primary_metrics` raw + `scaled:false` (Q2), filter gateway disabled (chuẩn bị M8)
- [x] `backend/app/api/gateways.py` (mới): `GET /gateways`, `GET/PATCH /gateways/{id}` (patch validate adapter_key theo registry → 422; POST/DELETE để M8), `GET /latest` (đa slave, slave chưa có dữ liệu → signals null), `GET /history` (Flux, `agg` raw|duration, window ≤7 ngày → 400 `range_too_large`, limit cap 20000), `GET /events` (con trỏ `before`, `next_before`, cap 200), `GET /diag` (+ note Q7)
- [x] `backend/app/stores/redis_reader.py` (mới): decode hash bytes→JSON values
- [x] `backend/app/stores/influx_query.py` (mới): `query_history` (+ `query_diag_latest`) chạy `to_thread` trên client sync; escape quote trong_flux literal
- [x] `backend/app/stores/postgres.py`: thêm readers `fetch_gateways/fetch_gateway/fetch_slaves/fetch_signal_defs/fetch_events/patch_gateway`
- [x] `backend/app/ingestion/persist.py`: **fix M3 thiếu** — info upsert giờ ghi meta `fw_version/hw_version/ip/mac` (COALESCE giữ giá trị cũ khi field vắng) → API detail/summary có meta
- [x] `backend/app/main.py`: mount 2 router + error handlers
- [x] `requirements-dev.txt`: `pytest-cov==7.1.0`
- [x] tests: `test_api_m4.py` (22 test httpx/ASGITransport, monkeypatch readers), `test_readers_m4.py` (redis decode + flux builder)

Tất cả route gắn `Depends(get_current_user)` stub (§4.5) — bật auth sau không đổi handler.

## 3. Kiểm chứng DoD (plan §7 M4)

| Tiêu chí | Cách đo | Kết quả | Đạt |
|---|---|---|---|
| JSON §4.1 đạt được bằng curl | 6 endpoint với dữ liệu simulator live | summary đúng shape ví dụ (badge online, fw 1.1.0, `primary_metrics:[{key:ai_raw, raw:14605, value:14605, scaled:false, unit:null}]`); latest/detail/list/events/diag/history đều khớp mẫu | ☑ |
| Badge `stale` khi dừng telemetry, MQTT vẫn online | paho probe publish retained `status online` (không gửi telemetry) | summary: `badge:"stale", state:"online", fresh:false`, `last_telemetry_at` giữ thời điểm gói cuối 13:17:39 | ☑ |
| Badge `offline` sau LWT < 5 s | `kill -9` probe (keepalive 2) | t+5 s: `badge:"offline", state:"offline"` (LWT `unexpected_disconnect`) | ☑ |
| Restart → hoạt động trở lại | chạy lại simulator | badge `online` trong 12 s | ☑ |
| `/api/v1/health` reflect từng store | `docker compose stop redis` | **503** `{"status":"degraded","checks":{...,"redis":false,...}}`; start lại → 200 ok | ☑ |
| Coverage test API > 80% | `pytest --cov=app/api` | **98%** (gateways 99%, dashboard 97%, common 95%, errors 94%) | ☑ |
| Case thiếu field `hc0` | test + live: `history?signals=ai_raw,di_0,hc0` | series `hc0: points:[]` (đường đứt quãng, không lỗi); latest không có hc0 vẫn render | ☑ |
| Tests | `pytest -q` | **49 passed**; ruff/black sạch | ☑ |

## 4. Bug gặp phải & cách sửa

1. **InfluxDB 2.7 Flux không có `typeof()`** (kế hoạch map bool→0/1 trong 1 query fail compile), và phiên bản `union` 2 nhánh trong 1 query fail runtime "type conflict: bool != int" (kiểm tra kiểu tĩnh của biến `base` dùng chung). **Fix:** `query_history` tách **2 flux độc lập** khi có `agg` — nhánh numeric (mean trực tiếp) + nhánh DI theo tiền tố `di_` (map bool→1.0/0.0 rồi mean) — merge kết quả phía Python. Hệ quả đã ghi nhận: bool signal không theo tiền tố `di_` (edge case `reg_*` kiểu bool) sẽ lỗi mean khi `agg≠raw` — raw vẫn OK; chấp nhận vì parser chỉ sinh bool cho `di_*`.
2. **`+00:00` trong query string** bị decode thành khoảng trắng → test phải dùng `Z` (client thật nên escape `%2B` hoặc dùng Z); handler trả 400 `invalid_request` rõ ràng cho input lỗi.
3. **M3 sót meta info**: cột `fw/hw/ip/mac` có trong schema nhưng upsert không ghi → summary/detail `fw_version:null`. Đã bổ sung (COALESCE để payload thiếu field không xóa giá trị cũ).

## 5. Ghi chú thiết kế

- `primary_metrics` = mọi signal numeric của slave đầu tiên trừ họ `di_*`; `display_name` fallback = key khi admin chưa khai báo `signal_defs` (không tự đặt tên tín hiệu — tránh đoán).
- `count` trong history response = **tổng điểm mọi series** (plan không chốt; ghi chú để frontend dùng `series[i].points.length`).
- Lỗi store (influx timeout) → 503 `store_unavailable`, không để traceback lọt ra client.
- Reader đặt trong `app/stores/*` cạnh writer; API layer chỉ trộn dữ liệu — giữ endpoint mỏng để M5 WS tái sử dụng `compute_badge`/readers.

## 6. Bước tiếp

- M5: WebSocket hub + snapshot dùng lại readers; broadcaster in-process.
- M8: POST/DELETE /gateways + UI admin (summary đã ẩn disabled từ M4).
