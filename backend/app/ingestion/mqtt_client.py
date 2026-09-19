import asyncio

from app.config import get_settings


async def tcp_check() -> bool:
    # M1: chỉ kiểm tra broker reachable qua TCP; client MQTT thật (aiomqtt) vào M2
    s = get_settings()
    try:
        async with asyncio.timeout(3):
            _, writer = await asyncio.open_connection(s.mqtt_host, s.mqtt_port)
            writer.close()
            await writer.wait_closed()
        return True
    except Exception:
        return False
