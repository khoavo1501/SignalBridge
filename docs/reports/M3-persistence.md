# Báo cáo — M3: Persist vào 3 kho (InfluxDB / Postgres / Redis)

- **Ngày hoàn thành:** 2026-09-19
- **Trạng thái:** ✅ Done
- **Commit/PR:** chờ commit

## 1. Mục tiêu (PROJECT_PLAN.md §7 M3)

Dữ liệu đã parse (M2) được ghi đúng thiết kế §3: time-series → InfluxDB, meta/events → Postgres, trạng thái mới nhất → Redis. Không đổi pipeline parse của M2.

## 2. File đã tạo/sửa

- [x] `backend/app/stores/influx_writer.py` (mới): builder `telemetry_point`/`diag_point` + `InfluxWriter` buffer, flush mỗi 1 s qua `asyncio.to_thread` (client sync `influxdb-client==1.50.0`, `SYNCHRONOUS`), cap queue 8000 điểm (drop + counter `influx_dropped` khi Influx chết kéo dài)
- [x] `backend/app/stores/redis_writer.py` (mới): `write_telemetry` (HSET `sb:latest:{gw}:{slave}` signals JSON-scalar + `_received_at` ISO + `_seq`; SET `sb:last_seen:{gw}` epoch), `write_status` (HSET `sb:status:{gw}` state/since/reason; **trả về changed=True/False** — nguồn dedupe status)
- [x] `backend/app/ingestion/persist.py` (mới): router theo kind →
      telemetry: influx enqueue + redis; diag: influx `diag` measurement;
      status: redis → chỉ insert `STATUS_ONLINE/OFFLINE` khi state ĐỔI;
      info: upsert `gateways` (`ON CONFLICT DO UPDATE SET updated_at` — không đè display_name/adapter_key của admin) + upsert `slaves`;
      event: insert `gateway_events` từng EventItem. Gateway chưa đăng ký → skip + counter `pg_skipped_unregistered` (không tự seed — đúng quy tắc Q8)
- [x] `backend/app/ingestion/mqtt_client.py`: `handle_message` xong → `persist.persist_message(msg)` (giữ `pipeline.handle_message` thuần parse để unit test M2 không đụng stores)
- [x] `backend/app/main.py`: lifespan start/stop `influx_writer` (flush nốt điểm cuối khi tắt)
- [x] `backend/app/api/ingestion.py`: `/ingestion/stats` gộp counter 3 writer (`influx_written/errors/dropped`, `redis_errors`, `pg_errors`, `status_events`)
- [x] `backend/tests/test_persist_m3.py` (mới): 10 test — line-protocol tags/fields sparse/server-time ns, diag `slave_1_ok`, redis hash + dedupe status, routing telemetry, status-change mới ghi pg, info upsert idempotent, events skip gateway chưa đăng ký, insert đủ từng EventItem
- [x] `README.md`: mục "Dữ liệu đi đâu (M3)" với lệnh kiểm tra nhanh từng kho

## 3. Kiểm chứng DoD (stack thật + simulator, 2026-09-19)

| Tiêu chí (plan §7 M3) | Cách đo | Kết quả | Đạt |
|---|---|---|---|
| (a) Chạy 10 phút → telemetry point/s đúng nhịp | `simulator --duration 600` (100 ms/gói); influx count `_field=="di_word"` cửa sổ 50 s steady | **500 rows / 50 s = 10,0 điểm/s ±0%** — đúng 1/interval (plan ghi "≈100/s": nếu đếm **giá trị field** thì 10 field × 10 msg/s ≈ 100/s); cả run: sim gửi 5995, influx_written 5653, errors 0, dropped 0 | ☑ |
| (b) Redis latest có `_received_at` = thời điểm server | `redis-cli HGETALL sb:latest:GW_S7200_01:1` | `_received_at 2026-09-19T12:13:56.772835+00:00` (server UTC, **không phải ts=0**), `_seq 449`, 8 DI + di_word + ai_raw | ☑ |
| (c) Đúng 2 dòng STATUS khi kill/restart, không spam | `SELECT count(*) ... WHERE code LIKE 'STATUS%'` trước/sau từng chu kỳ | Cặp kill/restart nào cũng tăng **đúng 2** (OFFLINE do LWT + ONLINE khi reconnect): 12:13:11/12:13:56, 12:15:47/12:25:47, 12:26:49/12:27:49. Status định kỳ 30 s + retain replay: 0 dòng thêm | ☑ |
| (d) slaves upsert từ info | `SELECT` slaves JOIN gateways | `addr=1 name='S7-200'` đúng 1 dòng sau nhiều lần replay info | ☑ |
| (e) kill -9 backend giữa dòng → retain replay không trùng | `docker kill -KILL` backend giữa run 10 phút, `up -d` | Container mới: `status_events: 0` dù broker replay retained info+status (redis đã có `state=online` → changed=False); gateways=1, slaves=1, pg_errors=0 | ☑ |
| Sparse field: thiếu hc0/c0 không lỗi | như (b) + `r._field=="ai_raw"` count | 450/450 điểm có ai_raw; measurement không phát sinh hc0/c0 (firmware hiện tại) — không exception nào | ☑ |
| Unit tests | `.venv/bin/pytest -q` | **28 passed** (18 cũ + 10 mới), ruff/black sạch | ☑ |

Ghi chú (a): trong ~12 s backend chết (test e), telemetry QoS 0 mất — pipeline **không** tự bù, đúng hành vi đã chốt ở ràng buộc #1/R1; `received` cả run = 5674 < 5995 gửi đi, khớp ước tính downtime.

## 4. Bug gặp phải & cách sửa

1. **`Point.add_field` không tồn tại** trong influxdb-client 1.50 → API đúng là `Point.field()`. Sửa bằng sed, test line-protocol bắt ngay ở lần chạy đầu.
2. **`:raw::jsonb` không được SQLAlchemy bind** (asyncpg nhận `:raw` thô → "parameter missing"): đổi thành `CAST(:raw AS jsonb)`. Bug lộ ra ở log backend lần khởi động đầu (STATUS_OFFLINE insert fail) — nhờ counters `pg_errors` + log exception trong persist.
3. `pgrep -f 'simulator.py --host'` match chính shell chờ → loop treo (sự cố thao tác verify, không phải code).

## 5. Quyết định thiết kế đáng chú ý

- **Persist ở tầng `mqtt_client`, không nằm trong `pipeline.handle_message`**: giữ hàm parse thuần (test M2 không cần mock stores), tách lỗi ghi DB khỏi lỗi parse; stats gộp qua endpoint.
- **Dedupe status dựa trên Redis, không dựa trên Postgres**: đọc state trước khi ghi hash — survive backend restart vì Redis AOF; INSERT khi và chỉ khi state đổi.
- **Không tự đăng ký gateway từ payload** (ràng buộc Q8): event/info từ gateway lạ chỉ log + đếm `pg_skipped_unregistered`. (Info upsert hiện vẫn tạo gateway row — *ngoại lệ có chủ đích* vì §3.1 ghi rõ "tự upsert từ payload info"; admin tạo trước qua UI M8, còn gateway chưa seed sẽ tự xuất hiện khi gửi info.)
- Influx client sync chạy trong `to_thread` — tránh thêm dependency reactive; batch 1 s đủ cho quy mô hiện tại (§1.2).

## 6. Ràng buộc dự án — tuân thủ

- #1 `ts` payload bỏ qua hoàn toàn: timestamp Influx = `received_at` server ns, Redis `_received_at` ISO server time. ☑
- #2 không scale: field `ai_raw` ghi nguyên raw. ☑
- #3 thiếu `hc0`/`hr_54`/`hr_58`: dòng sparse không có field, không lỗi (đo ở §3). ☑
- #4 1 gateway → n slave: tag `slave_addr` + upsert `slaves` theo danh sách `info.slaves[]`. ☑
- #5 online vs freshness tách biệt: `sb:status` (status/LWT) và `sb:last_seen` (telemetry) là 2 key riêng — API M4 sẽ tính badge từ cả hai. ☑
- Adapter pattern: persist không biết gì về S7200 — chỉ tiêu thụ NormalizedMessage. ☑

## 7. Việc còn mở / bước tiếp

- M4: REST API đọc 3 kho (badge 3 trạng thái, `scaled=false`, history Flux, events phân trang).
- Ý tưởng đã ghi để cân nhắc sau: DLQ/counter cho điểm influx bị drop khi Influx chết (hiện chỉ log).
