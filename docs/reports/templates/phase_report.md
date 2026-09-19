# Báo cáo — <M_ID>: <Tên phase / chức năng>

- **Ngày hoàn thành:** YYYY-MM-DD
- **Trạng thái:** ✅ Done / 🟡 Done có phần treo / ❌ Blocked
- **Commit/PR:** <hash hoặc link>

## 1. Mục tiêu (chiếu PROJECT_PLAN.md §7)

<copy mục tiêu của milestone, giữ nguyên>

## 2. Task đã thực hiện

- [x] <task — kèm đường dẫn file chính>
- [ ] <task chưa xong → nêu lý do, trỏ phần 5>

## 3. Kết quả kiểm chứng DoD

> Mỗi dòng DoD trong plan phải có: **lệnh đã chạy** + **kết quả thực tế** (paste output ngắn, screenshot nếu là UI). Không viết "đạt" suông.

| Tiêu chí DoD | Lệnh / cách kiểm tra | Kết quả thực tế | Đạt? |
|---|---|---|---|
|  |  |  | ☐ |

## 4. Phát hiện mới so với kế hoạch

<Những gì khác dự đoán khi code: payload thực tế khác báo cáo, behavior của broker/DB, ... Mỗi phát hiện nếu ảnh hưởng thiết kế → cập nhật PROJECT_PLAN.md (tăng phiên bản) và ghi rõ ở phần 6.>

## 5. Tồn đọng & rủi ro phát sinh

| Mục | Chi tiết | Xử lý ở đâu |
|---|---|---|
|  |  |  |

## 6. Câu hỏi cần team hardware/firmware trả lời

<Các Qx mới phát sinh — đồng thời thêm vào bảng "Câu hỏi mở" của REPORT_OVERVIEW.md>

## 7. Ảnh hưởng tới tài liệu

- [ ] Đã cập nhật `docs/reports/REPORT_OVERVIEW.md` (bảng trạng thái + quyết định + nhật ký)
- [ ] Đã cập nhật `PROJECT_PLAN.md` nếu thiết kế đổi (ghi rõ mục, tăng phiên bản)
- [ ] Đã thêm payload mẫu mới vào `docs/payloads/` (nếu có)
