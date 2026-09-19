"""Gateway simulator — phát lại payload GW_S7200_01 theo docs/payloads/.

Implement ở Milestone 2 (PROJECT_PLAN.md §7 M2): 5 loại message
(telemetry/status/info/diag/event), biến thể thiếu hr_54, LWT offline, retain info.
Env cấu hình: SIM_MQTT_HOST, SIM_MQTT_PORT, SIM_GATEWAY_ID, SIM_INTERVAL_MS (.env.example).
"""

import sys


def main() -> int:
    print("gateway_simulator sẽ được implement ở M2 (xem PROJECT_PLAN.md §7).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
