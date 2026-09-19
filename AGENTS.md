# AGENTS.md — SignalBridge

## BẮT BUỘC: đọc docs trước khi làm bất cứ việc gì

Ở **đầu mỗi phiên làm việc / mỗi lần nhận prompt**, trước khi khám phá code hay chạy lệnh, lần lượt đọc:

1. `docs/reports/REPORT_OVERVIEW.md` — tiến trình hiện tại, quyết định đã chốt, câu hỏi mở, rủi ro.
2. `PROJECT_PLAN.md` — kế hoạch thiết kế chi tiết (mục liên quan tới task đang làm).
3. `docs/reports/` — báo cáo các phase đã xong (nếu task liên quan tới phase trước).
4. `docs/payloads/` — **ground truth payload** từ gateway; mọi xử lý dữ liệu phải bám sát các báo cáo này.

Nếu REPORT_OVERVIEW.md mâu thuẫn với code hiện tại → tin REPORT_OVERVIEW về trạng thái là sai, kiểm tra code, rồi **sửa lại REPORT_OVERVIEW.md** cho khớp thực tế.

## Quy trình báo cáo (quản lý theo phase / theo chức năng)

- Hoàn thành một **phase (milestone M0–M7)** hoặc một **chức năng độc lập** → tạo báo cáo mới `docs/reports/<M_ID>-<ten-slug>.md` từ template `docs/reports/templates/phase_report.md`, trong **cùng lần commit** khép lại phase đó.
- **Luôn cập nhật `docs/reports/REPORT_OVERVIEW.md`** kèm theo: bảng trạng thái milestone, quyết định mới, câu hỏi mở mới, nhật ký cập nhật. Đây là file tiến trình dùng chung — không thay thế, chỉ bổ sung.
- Phát hiện làm thay đổi thiết kế → cập nhật `PROJECT_PLAN.md` (tăng số phiên bản ở header) rồi mới code tiếp phần bị ảnh hưởng.
- Nhận payload mẫu của gateway/loại firmware **mới** → lưu vào `docs/payloads/` TRƯỚC KHI viết parser adapter cho nó.

## Các quy tắc đã chốt của dự án (không tự ý đổi)

- Stack đã chốt, không đổi: FastAPI · React+TS+Vite+Recharts+lucide-react · PostgreSQL · InfluxDB · EMQX · Redis · Nginx · Docker Compose.
- `ts` trong payload gateway **luôn = 0** → chỉ dùng server receive time làm timestamp.
- Giá trị analog (`ai_raw`, `hc0`, `c0`): **tạm hiển thị raw, KHÔNG đoán công thức scale** — công thức chờ team hardware (Q2, Q3).
- Parser phải chịu được field vắng mặt (`hr_54`/`hr_58` có thể không tồn tại) — không raise.
- Không code cứng schema của GW_S7200_01 vào pipeline — mọi loại gateway đi qua adapter riêng, map về format nội bộ (PROJECT_PLAN.md §2).
- Không có cảnh báo email/SMS ở phase 1; auth chỉ là stub đã định vị chỗ gắn JWT (PROJECT_PLAN.md §4.5).
- Điểm nào chưa rõ trong payload/yêu cầu → liệt kê thành câu hỏi và ghi vào phần "Câu hỏi mở" của REPORT_OVERVIEW.md, **không tự đoán rồi code**.
