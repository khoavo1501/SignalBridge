import asyncio
import logging

import aiomqtt

from app.config import get_settings
from app.ingestion import pipeline

log = logging.getLogger("signalbridge.mqtt")


async def tcp_check() -> bool:
    s = get_settings()
    try:
        async with asyncio.timeout(3):
            _, writer = await asyncio.open_connection(s.mqtt_host, s.mqtt_port)
            writer.close()
            await writer.wait_closed()
        return True
    except Exception:
        return False


async def run_ingestion() -> None:
    """Vòng lặp subscribe devices/+/+ với reconnect — chạy nền trong FastAPI process."""
    s = get_settings()
    backoff = 1.0
    while True:
        try:
            async with aiomqtt.Client(
                hostname=s.mqtt_host, port=s.mqtt_port, identifier="signalbridge-backend"
            ) as client:
                await client.subscribe(s.mqtt_topic_filter)
                log.info(
                    "MQTT connected %s:%s topic=%s", s.mqtt_host, s.mqtt_port, s.mqtt_topic_filter
                )
                backoff = 1.0
                async for message in client.messages:
                    topic = str(message.topic)
                    payload = message.payload
                    if isinstance(payload, (bytes, bytearray)):
                        data = bytes(payload)
                    else:
                        data = bytes(str(payload), "utf-8")
                    await pipeline.handle_message(topic, data)
        except aiomqtt.MqttError as exc:
            log.warning("MQTT connection lost: %s — retry in %.1fs", exc, backoff)
        except Exception:
            log.exception("MQTT listener unexpected error — retry in %.1fs", backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30.0)
