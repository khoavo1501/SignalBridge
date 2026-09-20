# Báo cáo — M7: Frontend chi tiết từng gateway/slave

- **Ngày hoàn thành:** 2026-09-20
- **Trạng thái:** ✅ Done
- **Commit/PR:** _(ghi ở commit docs ngay sau commit feat)_

## 1. Mục tiêu (chiếu PROJECT_PLAN.md §7)

**Mục tiêu:** drill-down theo gateway → slave.
**Tasks:** route `/gateways/:id`; trang chi tiết: header meta (fw/hw/ip/mac/slaves — nguồn `info`), tab Telemetry (chart Recharts chọn signal + khoảng thời gian, gọi `/history`), tab Events (bảng phân trang), tab Diag (bảng thống kê + gap `seq` ước tính); per-slave selector (hỗ trợ n slave); WS cập nhật chart đang hiển thị.
**DoD:** chọn signal `ai_raw` khoảng 1 h, chart render < 1 s, có đủ điểm (đếm so với influx CLI); bảng events khớp DB; chart hiển thị đúng gap khi simulator phát biến thể thiếu `hc0` (đường đứt đoạn, không crash); responsive ≥ 1280px; mọi case lỗi (gateway 404, influx timeout) hiển thị thông báo, không white-screen.

> Bối cảnh: M6b đã dựng khung 5 route. Phần M7 còn lại được chốt và làm trong milestone này: WS đẩy trực tiếp vào chart đang xem, pills chọn signal, phân trang events sâu bằng con trỏ `before`, cột gap `seq` ở trang Chẩn đoán, trang 404, và các case lỗi.

## 2. Task đã thực hiện

- [x] `subscribeTelemetry` pub-sub trong `LiveContext` (ref Set, không re-render provider) — phát `TelemetryTick {gateway_id, slave_addr, seq, tsMs, signals}` mỗi frame telemetry — `frontend/src/state/LiveContext.tsx`
- [x] Viết lại `SlaveDetailPage` theo M7: 4 khoảng thời gian (15m/1h raw, 6h 10s, 24h 1m), pills chọn signal (universe = signal số không phải `di_` từ `/latest`), trục thời gian hợp nhất (Map theo mốc → signal vắng = null), WS tail nối vào chart giữa hai lần REST 15 s (cap 1200) — `frontend/src/pages/SlaveDetailPage.tsx`
- [x] Events phân trang sâu: nút "Tải thêm (cũ hơn)" dùng con trỏ `before` của API (200 sự kiện/lượt/device), gộp + dedup — `frontend/src/pages/EventsPage.tsx`
- [x] Cột "seq gap 1h*" ở trang Chẩn đoán: `/history?signals=seq&agg=raw` 1 h → `lost = Σ max(0, seq[i]−seq[i−1]−1)`, hiển thị % ước lượng (tooltip ghi rõ QoS 0 chỉ là ước lượng — R1) — `frontend/src/pages/DiagnosticsPage.tsx`
- [x] `NotFoundPage` + route `*` — `frontend/src/pages/NotFoundPage.tsx`, `App.tsx`
- [x] Fix badge slave nhấp "trễ" giả: `lastSeen = max(REST /latest, mốc WS tail gần nhất)` — REST refresh 15 s > ngưỡng stale 10 s khiến badge nháy trễ dù WS vẫn streaming
- [x] Fix `/history` gọi với `limit=20000` (mặc định 5000 đã bị chạm — xem §4)

## 3. Kết quả kiểm chứng DoD

| Tiêu chí DoD | Lệnh / cách kiểm tra | Kết quả thực tế | Đạt? |
|---|---|---|---|
| `ai_raw` 1 h render < 1 s, đủ điểm so influx CLI | `curl /history?signals=ai_raw&agg=raw&from=-1h` + `influx query count()` | API **0,105 s / 3066 điểm**; CLI cùng cửa sổ **3136 điểm** (lệch chỉ do mép cửa sổ vài giây); trên UI chart hiển thị **10.244 điểm · 1h** sau khi bỏ cap 5000 | ✅ |
| Bảng events khớp DB | `psql count(*) gateway_events` vs `GET /gateways/GW_S7200_01/events?limit=200` | **81 = 81**, `next_before` hoạt động: trang cũ hơn trả về sự kiện 19/09; nút "Tải thêm" trên UI ẩn khi hết dữ liệu cũ | ✅ |
| Gap `hc0` đứt đoạn, không crash | Dừng simulator → restart `--with-hr54` (hc0 = hr_54 chỉ có khi flag); chart 1h chọn ai_raw+hc0 | hc0 **"6119 điểm · 1h · 4125 mốc trống (gap)"** — đường đứt hoàn toàn đoạn 11:04→11:21 (ảnh screenshot), không crash, không console error | ✅ |
| WS cập nhật chart đang hiển thị | Đọc `.chart-sub` trước/sau 4 s khi chart mở | "802 điểm · 1h" → **"818 điểm · 1h"** (+16 điểm/4 s = đúng nhịp throttle 250 ms); giá trị hc0/ai_raw live cũng cập nhật | ✅ |
| Responsive ≥ 1280px | viewport browser-use 639 px → inject CSS force desktop (grid 220px + 1fr, sidebar hiện) | Layout sidebar + panel + chart grid đúng, không tràn; **hạn chế**: không có viewport thật ≥1280 trong môi trường test (như M6) | 🟡 |
| Lỗi không white-screen | `/gateways/KHONG_TON_TAI`; `/gateways/GW_S7200_01/slaves/99`; `docker stop influxdb` rồi mở slave detail; route lạ | error-box "gateway chưa đăng ký" / "slave 99 không tồn tại" / "influxdb query failed: Failed to resolve…" — phần Redis `/latest` vẫn hiển thị bình thường; route lạ → trang 404 có nút về dashboard | ✅ |
| Build TS strict | `npm run build` | sạch, 592 kB (cảnh báo chunk size — tồn đọng M6) | ✅ |

## 4. Phát hiện mới so với kế hoạch

1. **`/history` raw cắt điểm ở `limit` mặc định 5000 và flux giữ điểm CŨ NHẤT** — `_history_fluxes` raw là `|> sort(_time) |> limit(n)` (tăng dần rồi limit → khi vượt cap, mất điểm mới nhất, đúng phần đồ thị realtime cần). Sim 100 ms hiện viết ~5.031 điểm ai_raw/1h → đã chạm cap thật sự. Workaround frontend: `limit=20000`. Fix gốc thuộc backend (sort desc → limit → sort asc) — ghi backlog M8.
2. **`hc0`/`c0` là mapping của `hr_54`/`hr_58`** — simulator chỉ phát khi có `--with-hr54`. Độ thưa của hc0 so với ai_raw trong DB (906 vs 5031 điểm/h) là **đúng thiết kế Q3** (parser chịu field vắng), không phải bug pipeline.
3. **Khoảng "im lặng hoàn toàn" (gateway chết) không tạo đứt đoạn trên chart một-signal** — rows hợp nhất chỉ chứa mốc thời gian có dữ liệu; khi chỉ chọn hc0, đoạn downtime được nội suy liền line. Đứt đoạn hiển thị đúng khi có signal khác phủ cùng khoảng (chọn ai_raw + hc0). Ghi nhận là hành vi có chủ đích của trục hợp nhất; cải tiến "fill bucket theo giây" để M8 cân nhắc.
4. **Badge slave nhấp "dữ liệu trễ" giả giữa hai lần refresh REST** — refresh 15 s > ngưỡng stale 10 s. Sửa: `lastSeen = max(/latest, WS tail cuối)`. Sau fix: "online · last seen 0 s trước" ổn định khi WS streaming.

## 5. Tồn đọng & rủi ro phát sinh

| Mục | Chi tiết | Xử lý ở đâu |
|---|---|---|
| Backend `/history` truncation | flux raw limit giữ điểm cũ nhất thay vì mới nhất (xem §4.1) | M8 (kèm test httpx) |
| Endpoint events aggregate | `/api/v1/events` toàn hệ thống chưa có — UI đang lặp theo gateway (kế thừa M6) | M8 |
| Bundle 592 kB | code-split/manualChunks (kế thừa M6) | M8 hoặc sau M8 |
| Viewport thật ≥1280 | môi trường browser-use 639 px, mới verify bằng CSS ép | khi có máy display đủ rộng |

## 6. Câu hỏi cần team hardware/firmware trả lời

Không phát sinh câu hỏi mới. Q2b (công thức scale) và Q7 (nhãn biến đếm Modbus) vẫn mở như trong REPORT_OVERVIEW.

## 7. Ảnh hưởng tới tài liệu

- [x] Đã cập nhật `docs/reports/REPORT_OVERVIEW.md` (bảng trạng thái 8/9 + quyết định + nhật ký)
- [ ] `PROJECT_PLAN.md` không đổi thiết kế — không tăng phiên bản (hành vi §4.1/§4.2 giữ nguyên; limit là tham số API đã có)
- [x] Không có payload mẫu mới (biến thể `hr_54`/`hr_58` đã mô tả trong `docs/payloads/BAO_CAO_PAYLOAD_Gateway_S7200.md`)
