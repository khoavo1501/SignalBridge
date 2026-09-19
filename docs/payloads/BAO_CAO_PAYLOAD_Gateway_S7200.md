# Báo cáo phân tích Payload — Gateway_S7200

- **Thiết bị:** `GW_S7200_01`
- **Firmware:** 1.1.0
- **Phần cứng:** STM32F411 + W5500 (Ethernet) + RS485 (Modbus RTU, 9600 baud, slave ID 1)
- **Broker MQTT:** 192.168.1.4:1883 (Mosquitto, không TLS, không user/pass)
- **Định dạng topic:** `devices/GW_S7200_01/<category>`

## Tổng quan các payload

Gateway publish 6 loại payload JSON qua MQTT, tất cả đều chứa 2 field chung:

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `device_id` | string | `"GW_S7200_01"` |
| `ts` | uint32 | Unix timestamp (giây). Bằng 0 nếu NTP chưa đồng bộ (`GATEWAY_ENABLE_NTP = 0` nên hiện luôn là 0 hoặc uptime-based nếu bật NTP) |

---

## 1. Telemetry — topic `devices/GW_S7200_01/telemetry`

- **Điều kiện gửi:** chỉ khi **cả 2 region Modbus đọc OK** (poll mỗi 100 ms)
- **QoS 0, không retain**

```json
{
  "device_id": "GW_S7200_01",
  "ts": 1234567890,
  "type": "telemetry",
  "seq": 42,
  "fw": "1.1.0",
  "plc": {
    "di_word": 5,
    "di": [true,false,true,false,false,false,false,false,false,false,false,false,false,false,false,false],
    "ai": 12345
  },
  "registers": {
    "di_0": true, "di_1": false, "...": "...", "di_7": false,
    "hr_50": 12345,
    "hr_54": 123456789,
    "hr_58": 100
  }
}
```

### Cấu trúc chi tiết

| Field | Nguồn dữ liệu | Ghi chú |
|---|---|---|
| `seq` | `telemetry_seq` (tăng sau mỗi lần publish thành công) | Số thứ tự gói tin |
| `plc.di_word` | Modbus region 0, offset 0 (VW1000 / 40001) | Word đóng gói I0.0–I0.7 |
| `plc.di[0..15]` | Tách bit từ `di_word` | 16 bit, bit 0 = I0.0 … bit 7 = I0.7; bit 8–15 hiện luôn false (word 8 bit thấp từ VW1000) |
| `plc.ai` | Modbus region 1, offset 50 (VW1100 / AIW0) | Giá trị analog raw, chưa scale |
| `registers.di_N` | 8 signal đầu (`DI_BIT`, địa chỉ 0, bit 0–7) | Boolean |
| `registers.hr_50` | Signal U16, offset 50 (AIW0) | Giá trị 16-bit raw |
| `registers.hr_54` | Signal U32_LE, offset 54+55 (VW1108/VW1110 = HC0 low/high) | Ghép 2 thanh ghi: `(high << 16) \| low` → counter 32-bit |
| `registers.hr_58` | Signal U16, offset 58 (VW1116 = C0) | Counter 16-bit raw |

> Lưu ý: nếu bất kỳ signal nào không lookup được register (region chưa valid) thì signal đó bị **bỏ qua** (`continue`). Nếu tất cả signal đều bị bỏ qua → `writer.ok = 0` → **không publish telemetry**.

### Ràng buộc phía server
- `registers` phải chứa **1..200 giá trị** — hiện tại gateway gửi 11 giá trị (8 DI + 3 HR), thỏa mãn.
- Buffer tối đa `GATEWAY_JSON_MAX = 4096` byte. Payload hiện tại ước tính ~450–500 byte, dư an toàn.

---

## 2. Status — topic `devices/GW_S7200_01/status`

- **Điều kiện gửi:** khi MQTT kết nối thành công và mỗi 30 s (`GATEWAY_STATUS_INTERVAL_MS`)
- **QoS 1, retain = true**

```json
{
  "device_id": "GW_S7200_01",
  "ts": 1234567890,
  "type": "status",
  "state": "online",
  "uptime_s": 3600,
  "reason": "..."   // chỉ có khi lỗi, vd "unexpected_disconnect"
}
```

| Field | Ý nghĩa |
|---|---|
| `state` | `"online"` khi đang chạy; `"offline"` trong LWT |
| `uptime_s` | Số giây từ lúc boot |
| `reason` | Chỉ xuất hiện trong LWT: `"unexpected_disconnect"` |

### LWT (Last Will and Testament)

Khi kết nối MQTT, gateway đăng ký will trên chính topic `status`:

```json
{"device_id":"GW_S7200_01","ts":0,"type":"status","state":"offline","reason":"unexpected_disconnect"}
```

Broker sẽ publish payload này (retain) nếu gateway mất kết nối đột ngột.

---

## 3. Info — topic `devices/GW_S7200_01/info`

- **Điều kiện gửi:** ngay sau khi MQTT connect thành công (mỗi lần reconnect)
- **QoS 1, retain = true**

```json
{
  "device_id": "GW_S7200_01",
  "ts": 1234567890,
  "type": "info",
  "master": {
    "fw_version": "1.1.0",
    "hw_version": "STM32F411_W5500_RS485",
    "ip": "192.168.1.50",
    "mac": "02:53:37:20:00:01",
    "reset_reason": "POWER_ON",
    "slaves": [
      { "id": 1, "addr": 1, "name": "S7-200" }
    ]
  }
}
```

> Lưu ý: `reset_reason` luôn là chuỗi cứng `"POWER_ON"` — chưa đọc cờ reset thực của STM32 (thanh ghi RCC_CSR). Gateway chưa có lệnh disconnect chủ động trước reset/watchdog.

---

## 4. Diag — topic `devices/GW_S7200_01/diag`

- **Điều kiện gửi:** mỗi 10 phút (`GATEWAY_DIAG_INTERVAL_MS = 600000`)
- **QoS 0, không retain**

```json
{
  "device_id": "GW_S7200_01",
  "ts": 1234567890,
  "type": "diag",
  "stats": {
    "poll_cycle_ms": 100,
    "uptime_s": 3600,
    "slaves": [
      { "id": 1, "addr": 1, "ok": 12345, "fail": 6 }
    ],
    "tx_packets": 12340,
    "tx_failures": 6,
    "mqtt_reconnect": 3
  }
}
```

| Field | Nguồn | Ý nghĩa |
|---|---|---|
| `poll_cycle_ms` | `GATEWAY_POLL_INTERVAL_MS` (hằng số 100) | Chu kỳ poll cấu hình, **không phải** thời gian đo thực tế |
| `stats.slaves[].ok` | `modbus_ok` | Số chu kỳ poll thành công (cả 2 region) |
| `stats.slaves[].fail` | `modbus_fail` | Số chu kỳ poll thất bại |
| `tx_packets` | `telemetry_seq` | Số gói telemetry publish thành công (thực ra là biến đếm publish OK, không phải tổng TX MQTT) |
| `tx_failures` | `modbus_fail` | **Trùng số liệu với `slaves[].fail`** — đây là tránh lệch schema server |
| `mqtt_reconnect` | `mqtt_reconnect` | Số lần (re)connect MQTT thành công |

> `tx_packets` và `tx_failures` đang map sang biến đếm Modbus, không phải biến đếm TX MQTT thực. Nếu server cần số gói MQTT đã gửi thì cần thêm biến đếm riêng trong `Mqtt_Publish`.

---

## 5. Event (lỗi Modbus) — topic `devices/GW_S7200_01/event`

- **Điều kiện gửi:** khi poll Modbus fail, rate-limit 30 s (`GATEWAY_STATUS_INTERVAL_MS`)
- **QoS 1, không retain**

```json
{
  "device_id": "GW_S7200_01",
  "ts": 1234567890,
  "type": "event",
  "events": [
    {
      "code": "SLAVE_COMM_LOST",
      "severity": "critical",
      "message": "Modbus RTU read failed",
      "source": "slave:1"
    }
  ]
}
```

- Chỉ có **một mã sự kiện duy nhất**: `SLAVE_COMM_LOST`. Các lỗi cụ thể (timeout, CRC, exception, HAL) không được phân loại ra event riêng — chi tiết lỗi nằm ở `last_result`, `last_rx_bytes`, `last_uart_error` trong RAM nhưng **không publish**.

---

## Luồng hoạt động tổng thể

```
Boot
 ├─ ModbusRtu_Init (timeout 100 ms)
 ├─ W5500_Init (IP tĩnh 192.168.1.50)
 └─ Vòng lặp Gateway_Task:
     ├─ Mỗi 100 ms: poll_plc()
     │    ├─ Region 0: Read Holding Regs #0 qty 1 (VW1000 - DI)
     │    ├─ Region 1: Read Holding Regs #50 qty 1 (VW1100 - AIW0)
     │    ├─ OK cả 2  → publish telemetry (QoS 0)
     │    └─ Fail     → publish event SLAVE_COMM_LOST (rate-limit 30 s)
     ├─ W5500 fail → retry Init mỗi 5 s
     ├─ MQTT chưa connect → connect (kèm LWT) mỗi 5 s
     │    └─ Sau khi connect: publish info (retain) + status online (retain)
     ├─ Mỗi 30 s: publish status online (retain, QoS 1)
     └─ Mỗi 10 phút: publish diag (QoS 0)
```

---

## Vấn đề và rủi ro phát hiện được

1. **`ts` = 0 hoặc sai lệch:** NTP đang tắt (`GATEWAY_ENABLE_NTP = 0`) và broker trong LAN không cấp thời gian, nên `ts` luôn là 0. Server sẽ không sắp xếp dữ liệu theo thời gian thiết bị được. Khuyến nghị: bật NTP hoặc dùng timestamp từ broker (`$SYS` / server-side ingest time).
2. **`tx_packets`/`tx_failures` trong diag không đúng语义:** đang map từ biến đếm Modbus, không phải TX MQTT thực.
3. **`reset_reason` cứng "POWER_ON":** chưa đọc RCC_CSR; sau một lần reset bằng watchdog/IWDG vẫn báo POWER_ON.
4. **Thiếu mã event chi tiết:** chỉ có `SLAVE_COMM_LOST`, không phân biệt timeout/CRC/exception/HAL error dù dữ liệu đã có trong struct.
5. **`plc.di` có 16 phần tử nhưng chỉ 8 bit thấp có nghĩa** (word VW1000 đóng gói I0.0–I0.7; bit 8–15 luôn false). Server/dashboard cần biết chỉ 8 bit đầu hợp lệ.
6. **U32_LE counter `hr_54`:** `GATEWAY_POLL_REGIONS` hiện **không poll offset 54–55** (region 1 chỉ đọc offset 50, qty 1) → signal `hr_54` (HC0) và `hr_58` (C0) sẽ bị `lookup_register` fail và bị bỏ qua trong `registers`. **Nghĩa là telemetry hiện tại chỉ có 9 giá trị (8 DI + hr_50), không có hr_54/hr_58** — nếu cần counter phải mở rộng region: ví dụ region 1 → `{ 50, 9, 0x03 }` (đọc offset 50..58).
7. **Không có publish chủ động trạng thái offline khi tắt nguồn đúng cách:** chỉ có LWT. Không thấy lệnh gọi `Mqtt_Disconnect` trong luồng chính (chỉ định nghĩa).
8. **QoS không đồng bộ giữa status/info/event (QoS 1) và telemetry/diag (QoS 0):** telemetry có thể mất gói khi mạng chập chờn mà không phát hiện từ phía seq (seq chỉ tăng khi publish thành công, nhưng QoS 0 không đảm bảo broker nhận).

## Kết luận

Payload đúng chuẩn JSON, có schema ổn định với `type` discriminator, đúng quy ước topic `devices/<id>/<category>`, có LWT, retain cho info/status. Cần khắc phục các điểm (1), (2), (6) trước khi tích hợp dashboard/server vì chúng ảnh hưởng trực tiếp tới tính toàn vẹn dữ liệu và độ phủ tín hiệu.
