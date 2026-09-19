# SignalBridge — Giám sát PLC realtime

Web app giám sát realtime dữ liệu PLC qua gateway MQTT. Thiết kế chi tiết: [`PROJECT_PLAN.md`](PROJECT_PLAN.md) · Tiến trình: [`docs/reports/REPORT_OVERVIEW.md`](docs/reports/REPORT_OVERVIEW.md).

## Bắt đầu làm việc (đọc theo thứ tự)

1. `docs/reports/REPORT_OVERVIEW.md` — đang ở milestone nào, quyết định đã chốt, câu hỏi mở.
2. `PROJECT_PLAN.md` — thiết kế + milestones + DoD.
3. `docs/payloads/` — ground truth payload từ gateway.
4. `AGENTS.md` — quy tắc bắt buộc với agent/collaborator.

## Chạy local (phase hiện tại: M0 — chỉ scaffold)

Yêu cầu: Python ≥ 3.12, Node ≥ 22, Docker (từ M1).

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest                                   # 2 smoke tests
uvicorn app.main:app --reload            # http://localhost:8000/api/v1/healthz

# Frontend
cd frontend
npm install
npm run dev                              # http://localhost:5173
npm run build && npm run lint            # kiểm tra CI-local
```

Toàn bộ stack (EMQX, Postgres, InfluxDB, Redis, backend, frontend, Nginx) chạy bằng `docker compose up -d` **từ Milestone 1** — file `docker-compose.yml` chưa tồn tại ở M0.

## Cấu trúc

```
backend/            FastAPI: parsers/ ingestion/ stores/ api/ ws/
frontend/           React + TS + Vite (Recharts, lucide-react)
gateway_simulator/  Giả lập GW_S7200_01 publish MQTT (implement ở M2)
deploy/             nginx compose-level (M1)
docs/               payloads/ (ground truth) + reports/ (tiến trình)
```
