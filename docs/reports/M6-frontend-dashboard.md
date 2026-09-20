# Báo cáo — M6: Frontend dashboard tổng quan (+ M6b redesign theo tham chiếu admin IIoT)

- **Ngày hoàn thành:** 2026-09-19
- **Trạng thái:** ✅ Done (M6 + M6b)
- **Commit/PR:** `85bf10a` — feat: M6 frontend dashboard — 5 trang UI dark admin, socket WS dùng chung LiveProvider, badge 3 trạng thái client-side, sparkline + chart Recharts

## 1. Mục tiêu (chiếu PROJECT_PLAN.md §7)

Trang chủ nhìn thấy toàn bộ nhà máy.

**DoD (plan):** mở `http://localhost/` → thấy card `GW_S7200_01` online, giá trị `ai_raw` cập nhật liên tục; dừng gửi telemetry (giữ kết nối MQTT) → badge `stale` trong ≤ `STALE_THRESHOLD_S` + 1 nhịp UI; kill MQTT → `offline` < 5 s; đóng/mở tab không leak WS; `npm run build` không lỗi TS strict.

## 2. Task đã thực hiện

- [x] `frontend/src/api/types.ts` — type contract (§4.1 summary + §4.2 WS envelope) + type guard cấu trúc (`isSummary/isTelemetry/isStatus/isInfo`).
- [x] `frontend/src/api/client.ts` — `apiGet<T>` qua `/api/v1`, parse error contract `{"error":{code,message}}` → `ApiError`; lỗi mạng → code `network_error`.
- [x] `frontend/src/hooks/useGatewaySocket.ts` — WS same-origin `${wss|ws}://${location.host}/ws`, reconnect exponential backoff 1 s → cap 30 s, reset đếm khi open; cleanup gỡ handler trước `close()` để không reconnect rac khi unmount.
- [x] `frontend/src/state/live.ts` — `applyFrame` (snapshot thay toàn bộ; telemetry/status/info patch theo `gateway_id` đã biết), `mergeTelemetry` (bỏ `di_*`/bool, cập nhật hoặc thêm metric `scaled:false`), `badgeOf` tính lại phía client (ràng buộc #5).
- [x] `frontend/src/components/StatusBadge.tsx` — 3 nhãn Việt: Trực tuyến / Dữ liệu trễ / Kết nối ngắt + tooltip giải thích điều kiện.
- [x] `frontend/src/components/GatewayCard.tsx` — primary metrics `toLocaleString("vi-VN")`, hậu tố "(raw)" khi `!scaled && !unit`, thời gian tương đối + tuyệt đối, viền màu theo badge.
- [x] `frontend/src/pages/SummaryPage.tsx` — REST `/dashboard/summary` làm nền, WS snapshot/frames đè lên; tick 1 s recompute badge; chip trạng thái WS (Wifi/WifiOff); skeleton loading, error + nút thử lại, empty box (chờ M8).
- [x] `App.tsx` BrowserRouter route `/` (placeholder comment M7/M8); `main.tsx` import `index.css`; `vite.config.ts` dev proxy `/api`→`:8000`, `/ws`→`ws://:8000`.
- [x] Build production qua Docker + nginx (image frontend cũ, chỉ source đổi — `docker compose up -d --build frontend`).

### M6b — redesign theo tham chiếu admin IIoT (dark) cùng phiên

User đưa 5 screenshot tham chiếu (sidebar + topbar, KPI row, gateway card có sparkline, chi tiết gateway breadcrumb + bảng PLC + panel cảnh báo, chi tiết PLC có chart 15m/1h/6h/24h, bảng Diagnostics, Events filter + phân trang). Thiết kế lại toàn bộ UI theo stack đã chốt (React+TS+Vite+Recharts+lucide, vanilla CSS — không đổi thư viện):

- [x] `index.css` viết lại: design tokens dark-tech (nền `#0c0e12`, panel `#14171d`, accent amber duy nhất `#dfa24a`, ok/bad xanh/đỏ đã giảm bão hòa), radius phân tầng, mono cho mọi số/ID, media query <900px ẩn sidebar.
- [x] `components/Layout.tsx` — shell topbar (brand SB + chip DEMO + chip live WS) + sidebar 2 nhóm "Tổng quan"/"Hoạt động", `NavLink` active, footer ghi chú raw Q2; `Outlet` cho routing lồng.
- [x] `state/LiveContext.tsx` — **một socket WS dùng chung mọi route** (LiveProvider bọc BrowserRouter): seed REST summary, snapshot WS đè lên, sparkline per-gw (seed `/history` 3 phút agg 10 s + append frame telemetry số không phải `di_*`, cap 90), buffer `sessionEvents` (cap 300) + `sessionDiags` (cap 60) từ frame, tick 1 s cho badge.
- [x] `state/format.ts` — fmtNum vi-VN / fmtClock / fmtAgo (tách khỏi LiveContext để hết cảnh báo react-refresh).
- [x] 5 trang: `DashboardPage` (KPI online/slaves/cảnh báo 1 h + lưới card sparkline), `GatewayDetailPage` (breadcrumb, meta fw/hw/ip/mac/adapter, 4 StatCard, bảng PLC với badge per-slave suy từ độ tươi `received_at`, panel 5 cảnh báo gần nhất, **tự refresh REST 5 s**), `SlaveDetailPage` (pills tầm nhìn 15m/1h/6h/24h → `/history` agg tương ứng, chart Recharts line per signal, giá trị latest + nhãn (raw), refresh 15 s), `EventsPage` (lọc severity/device/code + tầm nhìn client-side, gộp REST per-gw với session buffer có dedupe, phân trang 25), `DiagnosticsPage` (bảng `/diag` per-gw + panel lịch sử diag từ frame WS vì backend chưa có endpoint history diag).
- [x] `types.ts` mở rộng theo contract đã đọc trong `app/api/gateways.py`: EventData/DiagData frames, GatewayRow/LatestSlave/HistoryResponse/EventsResponse/DiagResponse + guards `isEvent/isDiag`.
- [x] `App.tsx` routes: `/` `/events` `/diagnostics` `/gateways/:id` `/gateways/:id/slaves/:addr` (placeholder M8 giữ nguyên); xóa `SummaryPage.tsx`.

## 3. Kết quả kiểm chứng DoD

| Tiêu chí DoD | Lệnh / cách kiểm tra | Kết quả thực tế | Đạt? |
|---|---|---|---|
| `npm run build` không lỗi TS strict | `cd frontend && npm run build` | `tsc -b && vite build` sạch ngay lần đầu; 1591 modules, 168.40 kB JS (gzip 55.40 kB) | ☑ |
| lint/format | `npm run format && npm run lint` | prettier write, eslint 0 lỗi | ☑ |
| Mở `http://localhost/` thấy card online, `ai_raw` cập nhật liên tục | simulator `--duration 600` → screenshot + sample DOM 5 lần/800 ms qua CDP | card `GW_S7200_01` badge "Trực tuyến", chip "realtime"; `ai_raw` đổi liên tục: 13.855 → 13.772 → 23.333 → 7.846 → 17.623 (nhịp throttle 250 ms, suffix "(raw)") | ☑ |
| Dừng telemetry (giữ MQTT online) → stale ≤ 10 s + 1 nhịp UI | simulator không có chế độ pause telemetry → kill -9 rồi publish retained `status=online` thủ công (paho, 1 dòng) để tái hiện đúng trạng thái "broker online, không telemetry" | badge chuyển "Dữ liệu trễ" (viền vàng) ngay khi nhận status frame — telemetry đã dừng 53 s ≫ ngưỡng 10 s; bộ đếm "telemetry cuối: N s trước" tăng đúng 1 nhịp/s | ☑ |
| Kill MQTT → offline < 5 s | `kill -9 <simulator pid>` lúc 21:17:52; backend log UTC + DOM poll | LWT offline xử lý lúc 14:17:52.477Z (**~0,5 s** sau kill); badge "Kết nối ngắt" viền đỏ | ☑ |
| Đóng/mở tab không leak WS | `GET /api/v1/ingestion/stats` → `ws_clients`; mở thêm 2 WS thô từ trang rồi đóng; reload tab | 1 → 3 (khi 2 WS mở) → 1 (sau close 0,8 s); reload nhiều lần `ws_clients` vẫn = 1 | ☑ |
| (bonus) Reconnect phía client | `docker compose restart backend` khi tab đang mở | chip về "realtime" sau backoff 1 s, `ws_clients` = 1, snapshot tự load lại | ☑ |

Backend regression: `pytest -q` → **69 passed** (không đổi code backend trong M6).

### Kiểm chứng M6b (redesign) — vẫn qua nginx thật, simulator `--fail-rate 0.02 --diag-interval-s 30`

| Tiêu chí | Cách kiểm tra | Kết quả thực tế | Đạt? |
|---|---|---|---|
| 5 trang render đúng tham chiếu | screenshot từng route qua CDP | Dashboard (KPI 1/1, cảnh báo đỏ, sparkline amber đang chảy), GatewayDetail (breadcrumb, meta, 4 StatCard, bảng PLC `ai_raw 24.077 / di_word 158`, panel 13 cảnh báo), SlaveDetail (chart `ai_raw · 3330 điểm · 1h`, pill range), Events (36 dòng, phân trang 1/2), Diagnostics (bảng /diag + history) | ☑ |
| Events filter hoạt động | click severity `info` | 36 → 23 dòng, chỉ còn STATUS_ONLINE/OFFLINE; pill code mono + device select render đúng | ☑ |
| Diag history từ WS frame | mở Diagnostics khi diag interval 30 s chạy | bảng REST snapshot + panel history nhận frame mới sau 30 s (dòng 22:07:31 xuất hiện khi chưa reload) | ☑ |
| Badge per-slave không kẹt "trễ" | để GatewayDetail mở 1 phút | sau fix auto-refresh 5 s: badge PLC giữ "online", seq tăng 4.083, last seen "1 s trước" | ☑ |
| Đủ 3 trạng thái badge trên UI mới | kill simulator → LWT; publish retained `status=online` không telemetry; bật lại simulator | offline sau ~0,5 s (card viền đỏ) → "dữ liệu trễ" sau ngưỡng 10 s + 1 nhịp → "online" khi telemetry chạy lại; tất cả không reload trang | ☑ |
| Không leak WS với SPA nhiều route | 5 lần hard-reload + chuyển route, đếm `ws_clients` | số connection ổn định (1 live/socket dùng chung), mở WS thô +1 → đóng −1 về cũ; `ws_dropped=0`, `parse_errors=0` | ☑ |
| Build sạch lần cuối | `npm run format && npm run lint && npm run build` | eslint 0 lỗi 0 cảnh báo (duy nhất 1 disable comment có lý do cho pattern context+hook); `tsc -b` strict sạch; dist 589 kB (gzip 171 kB — Recharts, có thể code-split khi cần) | ☑ |

## 4. Phát hiện mới so với kế hoạch

- **Thiếu chế độ "pause telemetry" trong simulator** — DoD "dừng telemetry giữ kết nối MQTT" không test được trực tiếp; tái hiện bằng retained `status=online` publish tay. Ghi nhận để M7/bảo trì: thêm `--pause-after N` vào simulator nếu cần test stale thường xuyên.
- **Badge tính phía client là bắt buộc để đạt "≤ ngưỡng + 1 nhịp UI"**: server chỉ gửi event frame (status đổi), không gửi frame mỗi giây — nếu chờ server thì transition online→stale không có frame nào trigger. Giải pháp: tick 1 s gọi `badgeOf(state, lastSeenMs, thresholdS)` — không đổi protocol, khớp ràng buộc #5.
- **Frame của gateway chưa biết (event/diag/telemetry trước snapshot) bị bỏ qua ở trang tổng quan** — trang chỉ render danh sách từ snapshot/REST; gateway mới đăng ký chỉ xuất hiện sau snapshot kế tiếp (reconnect) — chấp nhận được với phạm vi M6, M7/M8 sẽ xử lý refresh danh sách.
- `toLocaleString("vi-VN")` render `10571` thành `10.571` (dấu chấm phân cách nghìn) — nhất quán với convention số Việt Nam, giữ nguyên.
- **(M6b) Một connection WS "zombie" quan sát được sau nhiều lần teardown bất thường khi test**: `ws_clients` giữ ổn định 1 live + 1 stale, stale không được uvicorn ping (30/10 s) thu hồi vì nginx giữa upstream TCP vẫn ESTABLISHED. Không phải leak hệ thống (5 reload liên tiếp không tăng, đóng tab về 1, `ws_dropped=0`) — nhưng nên thêm `proxy_read_timeout` dài + `proxy_send_timeout` cho location `/ws` và cân nhắc giới hạn số conn mỗi IP ở M8 khi có auth.
- **(M6b) Backend chưa có endpoint tổng hợp**: lịch sử diag per-gateway (trang Diagnostics phải đệm từ WS frame trong phiên, mất khi reload) và events toàn cục (EventsPage phải gọi `/events` per-gateway rồi gộp + dedupe phía client). Nếu số gateway tăng, thêm `GET /api/v1/events` gộp sẵn — ghi vào backlog M8.
- **(M6b) Viewport môi trường test chỉ 639 CSS px** → sidebar bị media query <900px ẩn; layout desktop được verify bằng cách tạm inject style ép sidebar/stat-row hiển thị (screenshot đạt), không phải code khác.

## 5. Tồn đọng & rủi ro phát sinh

| Mục | Chi tiết | Xử lý ở đâu |
|---|---|---|
| Danh sách gateway không tự refresh | Gateway đăng ký mới chỉ hiện sau snapshot kế tiếp | M8 (admin CRUD + refresh) |
| Simulator thiếu pause telemetry | Xem §4 | M7 (tiện ích test) |
| Lịch sử diag chỉ trong phiên (M6b) | Trang Diagnostics đệm frame WS, reload là mất; backend chưa có endpoint history diag | M8 hoặc khi có nhu cầu — thêm `GET /gateways/{id}/diag/history` |
| Events gộp phía client (M6b) | EventsPage gọi `/events` per-gateway; nhiều gateway sẽ nặng | Thêm `GET /api/v1/events` tổng hợp (backlog M8) |
| Bundle 589 kB (gzip 171 kB) | Recharts chiếm phần lớn — hết ngưỡng cảnh báo của rollup | Code-split route khi trang admin M8 thêm deps |

## 6. Câu hỏi cần team hardware/firmware trả lời

Không có câu hỏi mới. Q2b (công thức scale) vẫn mở — UI đã chèn sẵn nhãn "(raw)" để đổi sang đơn vị thật khi có công thức mà không sửa layout.

## 7. Ảnh hưởng tới tài liệu

- [x] Đã cập nhật `docs/reports/REPORT_OVERVIEW.md` (bảng trạng thái 7/9 + quyết định badge client-side + nhật ký M6/M6b)
- [x] `PROJECT_PLAN.md` không đổi thiết kế (làm đúng §4.1/§4.2/§7-M6 đã chốt) — redesign M6b chỉ thay layout/mỹ thuật trên cùng contract REST+WS, không tăng phiên bản
- [x] Không có payload mẫu mới
- [x] `README.md`: mục frontend đã cập nhật danh sách 5 route + kiến trúc socket dùng chung sau M6b
