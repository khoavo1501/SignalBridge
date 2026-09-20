# Báo cáo — PERF: chống lag chart slave + cửa sổ trượt realtime

- **Ngày hoàn thành:** 2026-09-20
- **Trạng thái:** ✅ Done
- **Commit/PR:** `1038126`
- **Nguồn yêu cầu:** user report 2026-09-20 — "giật lag khi để dữ liệu trong 1h" + "reload lại trang thì chart trong dashboard lại chạy lại, hiển thị như cửa sổ trượt, nếu ban đầu chưa có dữ liệu thì giá trị 0"

## 1. Mục tiêu

Loại bỏ giật lag chart drill-down slave ở cửa sổ dài mà vẫn giữ đầy đủ hành vi M7 (WS cập nhật chart đang xem, gap `hc0` đứt đoạn, badge per-slave), và làm chart/sparkline load vào là ở trạng thái "đầy" ngay thay vì quét lại từ đầu.

## 2. Nguyên nhân gốc (chẩn đoán)

| Triệu chứng | Nguyên nhân |
|---|---|
| Giật khi chọn 1h | `agg=raw` → ~5.000–10.000 điểm/signal render SVG `type="monotone"` (spline đắt), mỗi WS tick 250 ms re-merge Map hàng nghìn điểm + re-render |
| "Chạy lại" khi refresh | `load()` REST 15 s gọi `setTail([])` → mép phải chart bị xóa rồi quét lại từ điểm REST cuối |
| Sparkline gõ lại từ trái | seed `/history` chỉ ~18 điểm rồi lớn dần qua WS tới cap 90 |

## 3. Task đã thực hiện

- [x] `frontend/src/pages/SlaveDetailPage.tsx` — mọi cửa sổ dùng agg backend: 15m→`2s`(450), 1h→`5s`(720), 6h→`10s`(2160), 24h→`1m`(1440) (Cách 1 user duyệt)
- [x] Lưới thời gian cố định `[gridStart, anchor]` với `anchor = floor(nowMs/interval)*interval` — memo phụ thuộc `anchor` nên đồ thị trượt đúng 1 lần mỗi ô agg, không mỗi giây; `XAxis domain={[gridStart, anchor]}`
- [x] WS tail bucket latest-wins theo ô agg (`SlaveDetailPage.tsx` effect `subscribeTelemetry`) + `TailPoint.raw` giữ tsMs thật cho badge (không bị "stale" giả ở cửa sổ 24h ô 1m)
- [x] Leading slots trước điểm dữ liệu đầu tiên = **0** (user yêu cầu); gap giữa chừng vẫn `null` → giữ thiết kế đứt đoạn hc0/c0 của M7; đếm `points/nulls` trong memo thay vì filter lại `rows` mỗi render
- [x] Bỏ `setTail([])` trong `load()` — REST refresh không còn xóa đuôi WS
- [x] `frontend/src/state/LiveContext.tsx` — sparkline seed `agg=2s`/180 s + **trái-pad 0 đủ SPARK_CAP=90** → đầy chiều rộng ngay khi tải, WS `slice(-90)` biến nó thành cửa sổ trượt
- [x] Tài liệu vận hành kèm phiên: `HUONG-DAN-SETUP-VA-DEPLOY.md` (hướng dẫn setup/deploy toàn tập)

## 4. Kết quả kiểm chứng

| Tiêu chí | Lệnh / cách kiểm tra | Kết quả thực tế | Đạt? |
|---|---|---|---|
| 1h không còn hàng nghìn điểm | UI `/gateways/GW_S7200_01/slaves/1` đọc `.chart-sub` | `518 điểm · 1h · 202 mốc đứt gãy` = 720 ô (trước: raw ~5.000+) | ☑ |
| Cửa sổ trượt đúng nhịp | so tick trục X cách nhau 6 s | tick đầu `12:30` → `12:31` (đúng +1 phút hiện thực, không nhảy cục bộ) | ☑ |
| Leading = 0 | chọn 24h khi data mới có ~1h | `180 điểm · 24h · 913 mốc đứt gãy` → 347 ô còn lại = 0 đệm trái, không crash | ☑ |
| Reload không "chạy lại" | UI `/` đếm điểm `svg.spark polyline` | đúng **90 điểm, x0=0.0** ngay sau load; slave page không còn reset tail mỗi 15 s | ☑ |
| Badge per-slave giữ nguyên | panel head trên slave page với sim mới | `online`, giá trị đổi liên tục giữa 2 lần REST | ☑ |
| Gap hc0 giữa chừng vẫn đứt | `.chart-sub` các signal | `nulls` đếm riêng, `connectNulls=false` giữ nguyên | ☑ |
| Build/lint | `prettier --check src` · `eslint --max-warnings 0` · `tsc -b && vite build` | sạch, build 2.7 s | ☑ |
| Regression toàn dự án | `pytest -q` · `ruff check app tests` · `black --check app tests` | 83 passed / All checks passed / 44 files unchanged | ☑ |
| Stack live | `docker compose ps` · `/api/v1/health` · `e2e_ws.py rate` | 7 service healthy; health ok 4 checks; WS 41 frame/10 s nhịp **250 ms PASS** | ☑ |
| Error contract | curl 404 gateway / 400 agg / 404 slave | `gateway_not_found` / `invalid_request` / `slave_not_found` đúng thân lỗi | ☑ |
| Smoke 4 route UI | điều hướng SPA `/events` `/diagnostics` `/admin` `/khong-ton-tai-xyz` | tiêu đề đúng, 404 render, không error-box, console 0 error | ☑ |

## 5. Phát hiện mới so với kế hoạch

- **Bug tìm ra ngay trong verify:** `nSlots = floor(windowS / intervalMs)` chia giây cho ms → mọi chart trả 0 điểm; sửa thành `s * 1000 / interval`. Nhắc lại bài học: phải verify trên stack live, lint/build không bắt được.
- Bucket theo ô agg làm mốc WS lùi tối đa `interval` (60 s ở 24h) → nếu dùng `t` đã bucket cho độ tươi thì badge thành "stale" giả → tách `TailPoint.raw` (tsMs thật) cho badge, `t` bucket chỉ dùng cho lưới chart.
- `requestAnimationFrame` không đo được FPS qua browser tool khi tab hidden (`document.hidden=true`) — dùng đếm điểm + trôi trục làm bằng chứng thay thế.
- Simulator hết `--duration` giữa các phiên là nguồn "0 điểm" giả khi verify — kiểm tra `pgrep simulator.py` trước khi kết luận lỗi UI.

## 6. Tồn đọng & rủi ro phát sinh

| Mục | Chi tiết | Xử lý ở đâu |
|---|---|---|
| Bundle 603 kB | không đổi (Recharts vẫn là main weight) | backlog sau M8 |
| 6h window = 2160 điểm/chart | agg `10s`; nếu còn phản hồi chậm có thể nâng `20s` chỉ bằng đổi `RANGES` | theo dõi phản hồi user |
| Sparkline trộn granularity | seed 2 s + WS tick 250 ms trên cùng mảng 90 (index-based như cũ) — chấp nhận cho sparkline, không phải chart | không xử lý phase 1 |

## 7. Ảnh hưởng tới tài liệu

- [x] Đã cập nhật `docs/reports/REPORT_OVERVIEW.md` (quyết định mới + nhật ký)
- [x] Thêm `docs/reports/HUONG-DAN-SETUP-VA-DEPLOY.md` (không đổi thiết kế → `PROJECT_PLAN.md` giữ nguyên)
- Không đổi backend/API — payload ground truth `docs/payloads/` không liên quan
