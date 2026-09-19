from app.parsers.base import GatewayAdapter
from app.parsers.s7200_v1 import S7200Adapter

# Đăng ký parser mới: thêm instance vào list này + set adapter_key trong DB (§2.4)
ADAPTERS: list[GatewayAdapter] = [S7200Adapter()]

BY_KEY: dict[str, GatewayAdapter] = {a.key: a for a in ADAPTERS}


def get_by_key(adapter_key: str) -> GatewayAdapter | None:
    return BY_KEY.get(adapter_key)


def resolve_by_match(gateway_id: str, topic: str, payload: dict) -> GatewayAdapter | None:
    for adapter in ADAPTERS:
        try:
            if adapter.match(gateway_id, topic, payload):
                return adapter
        except Exception:
            continue
    return None
