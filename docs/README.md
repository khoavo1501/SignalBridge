# docs/ — Cấu trúc tài liệu dự án

```
docs/
├── payloads/                     # Ground truth từ gateway/firmware — CHỈ THÊM, KHÔNG SỬA về sau
│   └── BAO_CAO_PAYLOAD_Gateway_S7200.md
└── reports/
    ├── REPORT_OVERVIEW.md        # ⭐ File tiến trình tổng quan — đọc ĐẦU TIÊN mỗi phiên, cập nhật MỖI commit kết thúc phase
    ├── templates/
    │   └── phase_report.md       # Template cho mỗi báo cáo phase/chức năng
    └── <M_ID>-<slug>.md          # Báo cáo chi tiết, ví dụ: M02-mqtt-ingestion.md
```

Quy tắc đầy đủ: `AGENTS.md` (bắt buộc đọc docs trước) và `PROJECT_PLAN.md` §6.

Tóm tắt vòng lặp:

1. Đọc `reports/REPORT_OVERVIEW.md` → biết đang ở phase nào, có gì blocked.
2. Làm phase/chức năng theo `PROJECT_PLAN.md` §7.
3. Xong → viết `reports/<M_ID>-<slug>.md` theo template + cập nhật `REPORT_OVERVIEW.md`, cùng commit.
