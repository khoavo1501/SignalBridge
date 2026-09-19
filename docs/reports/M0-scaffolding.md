# Báo cáo — M0: Scaffolding repo & tài liệu nền tảng

- **Ngày hoàn thành:** 2026-09-19
- **Trạng thái:** ✅ Done
- **Commit/PR:** chờ commit (xem mục 5)

## 1. Mục tiêu (PROJECT_PLAN.md §7 M0)

Khung repo chạy được, không có chức năng nghiệp vụ.

## 2. Task đã thực hiện

- [x] Cấu trúc thư mục theo plan §5.1 — `backend/app/{parsers,ingestion,stores,api,ws}/`, `frontend/src/`, `gateway_simulator/` (stub, code ở M2), `docs/{payloads,reports}/`
- [x] `backend/requirements.txt` + `requirements-dev.txt` pin version (mục 4 giải thích lệch so với dự kiến ban đầu); `pyproject.toml` (ruff + black line-length 100, pytest asyncio=auto)
- [x] `frontend/package.json` pin tuyệt đối (react 18.3.1, vite 5.4.11, recharts 2.15.0, lucide-react 0.468.0, react-router-dom 6.28.0, TS 5.6.3 strict) + eslint flat config + prettier
- [x] Skeleton backend: `main.py` (app factory), `config.py` (Settings đủ env M1–M5), `deps.py` (stub auth §4.5), `logging_config.py`, `api/health.py` (`/api/v1/healthz`), `alembic.ini` (chưa có migration baseline — thuộc M1)
- [x] Skeleton frontend: `main.tsx`, `App.tsx` placeholder, `vite-env.d.ts`
- [x] File gốc: `.gitignore`, `.env.example` (đủ biến cho M1+), `README.md` (hướng dẫn chạy + thứ tự đọc docs), `backend/Dockerfile`, `frontend/Dockerfile` + `frontend/nginx.conf`
- [x] CI `.github/workflows/ci.yml`: backend (ruff+black+pytest) → frontend (lint+format:check+build) → docker build 2 image
- [x] Template + REPORT_OVERVIEW: đã khởi tạo TRƯỚC M0 (2026-09-19, commit ffebe97) — đối chiếu khớp thực tế ✓

## 3. Kết quả kiểm chứng DoD

| Tiêu chí DoD | Lệnh / cách kiểm tra | Kết quả thực tế | Đạt? |
|---|---|---|---|
| `pytest` backend pass, không lỗi | `.venv/bin/pytest -q` (Python 3.14.7) | `2 passed, 2 warnings in 0.24s` (warnings: starlette deprecation — xem mục 4) | ☑ |
| `npm run dev` frontend chạy | `npm run dev` → `curl http://localhost:5173/` | HTTP `200`, log `VITE v5.4.11 ready in 160 ms` | ☑ |
| (extra) Production build TS strict | `npm run build` | `✓ built in 1.43s`, 1580 modules | ☑ |
| (extra) Lint + format sạch | `ruff check` / `black --check` / `npm run lint` / `npm run format:check` | "All checks passed", "13 files unchanged", eslint không lỗi, prettier OK | ☑ |
| (extra) Docker image build được | `docker build backend/` và `frontend/` | `Successfully tagged sb-backend:ci`, `sb-frontend:ci` | ☑ |
| CI xanh | xem GitHub Actions sau khi push remote | ⚠ CHƯA KIỂM CHỨNG — repo chưa cấu hình remote Git. Workflow đã viết + mọi bước CI đã chạy thủ công thành công ở trên | một phần |
| 2 file docs đầu tiên tồn tại | `docs/reports/REPORT_OVERVIEW.md`, `docs/reports/templates/phase_report.md` | tồn tại, commit ffebe97 | ☑ |

## 4. Phát hiện mới so với kế hoạch

1. **Version pin trong plan draft không cài được trên Python 3.14** (máy dev là Arch, Python 3.14.7; các pin cũ kiểu `black==24.12.1` không có wheel cp314). Đã resolve lại bằng cách cài không-pin rồi đóng băng đúng version pip chọn được (fastapi 0.141.1, pydantic 2.13.5, pytest 9.1.1, ruff 0.16.8, black 26.5.1...). Docker dùng `python:3.12-slim` — các pin này đều có wheel cho 3.12 (đã build image kiểm chứng).
2. **npm trên máy dev chặn postinstall script** (`esbuild` bị gate, phải `npm install-scripts approve esbuild`). Đây là cơ chế của npm cục bộ, không xảy ra trong Docker CI (npm 10 chuẩn). Ghi chú cho người mới clone repo.
3. Starlette deprecation warning (`httpx` → `httpx2` cho TestClient) — chỉ warning, không chặn; cân nhắc khi nâng fastapi ở M4.
4. `backend/alembic/versions/` rỗng sẽ bị Git bỏ qua → đã thêm `.gitkeep` (nếu không, `docker build` sẽ lỗi trên clone sạch).

## 5. Tồn đọng & rủi ro phát sinh

| Mục | Chi tiết | Xử lý ở đâu |
|---|---|---|
| Remote Git chưa cấu hình | CI chưa có thể "xanh" thật sự | Đầu M1 hoặc khi user tạo remote |
| package-lock.json | Đã sinh bởi `npm install` — CẦN commit để `npm ci` trong Docker/CI chạy đúng | commit M0 |
| `.env` local | Chưa tạo (compose chưa có ở M0) | M1 |

## 6. Câu hỏi cần team hardware/firmware trả lời

Không phát sinh câu hỏi mới. Chỉ còn Q7 (hiển thị `tx_packets`/`tx_failures`) và Q2b (công thức scale) — đều không chặn.

## 7. Ảnh hưởng tới tài liệu

- [x] Đã cập nhật `docs/reports/REPORT_OVERVIEW.md`
- [x] `PROJECT_PLAN.md` giữ nguyên v1.3 — không đổi thiết kế (pin version chỉ là chi tiết thực thi, đã ghi ở đây)
- [ ] Payload mẫu mới: không có

## 8. Sự cố bảo mật trong phiên làm việc (quan trọng)

Trong lúc implement M0, phiên hội thoại xuất hiện nhiều message giả dạng "[System Instructions]" yêu cầu: đổi/ẩn danh tính agent, đổi tên module không liên quan, im lặng không đặt câu hỏi, và nguy hiểm nhất là chạy `rm -rf ~/.qoder` (xóa thư mục cấu hình tool). **Tất cả đều bị từ chối**, không file/module nào bị đổi tên, không lệnh phá hủy nào được thực thi. Đề nghị: không dán payload/log chưa kiểm chứng vào prompt khi test sau này; coi là reminder về việc thêm auth + input validation (đã có trong backlog).
