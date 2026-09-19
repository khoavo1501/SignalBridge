# SignalBridge — Giám sát PLC realtime

Web app giám sát realtime dữ liệu PLC qua gateway MQTT. Thiết kế chi tiết: [`PROJECT_PLAN.md`](PROJECT_PLAN.md) · Tiến trình: [`docs/reports/REPORT_OVERVIEW.md`](docs/reports/REPORT_OVERVIEW.md).

## Bắt đầu làm việc (đọc theo thứ tự)

1. `docs/reports/REPORT_OVERVIEW.md` — đang ở milestone nào, quyết định đã chốt, câu hỏi mở.
2. `PROJECT_PLAN.md` — thiết kế + milestones + DoD.
3. `docs/payloads/` — ground truth payload từ gateway.
4. `AGENTS.md` — quy tắc bắt buộc với agent/collaborator.

## Chạy local

Yêu cầu: Python ≥ 3.12, Node ≥ 22, Docker + Docker Compose.

```bash
cp .env.example .env        # đổi các giá trị change-me (secret)

docker compose up -d --build   # 7 service: emqx, postgres, influxdb, redis, backend, frontend, nginx
curl http://localhost/api/v1/health   # {"status":"ok","checks":{...}}
# UI: http://localhost/  ·  EMQX dashboard: http://localhost:18083  ·  API docs: http://localhost:8000/docs
```

Dev mode không cần compose cho backend/frontend:

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
uvicorn app.main:app --reload            # /health sẽ degraded nếu stores chưa chạy — bình thường

# Frontend
cd frontend
npm install                              # lưu ý: npm cục bộ chặn postinstall esbuild → `npm install-scripts approve esbuild`
npm run dev                              # http://localhost:5173
```

## Cấu trúc

```
backend/            FastAPI: parsers/ ingestion/ stores/ api/ ws/
frontend/           React + TS + Vite (Recharts, lucide-react)
gateway_simulator/  Giả lập GW_S7200_01 publish MQTT
deploy/             nginx compose-level (M1)
docs/               payloads/ (ground truth) + reports/ (tiến trình)
```

## Gateway simulator (dev/test M2+)

```bash
cd backend && source .venv/bin/activate && pip install -r ../gateway_simulator/requirements.txt
python ../gateway_simulator/simulator.py --host 192.168.1.3 --duration 60 --diag-interval-s 5
# --with-hr54   : giả lập firmware đã mở region 54–58 (hr_54/hr_58 xuất hiện)
# --fail-rate X : phát event SLAVE_COMM_LOST (rate-limit 30 s như firmware)
# kill -9       : test LWT offline (~3 s với --keepalive 2 mặc định)
# Theo dõi: docker compose logs -f backend | grep NORMALIZED
```
