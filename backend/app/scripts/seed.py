"""Idempotent seed: user admin + gateway mẫu GW_S7200_01 (M1).

Auth chưa enforce phase 1 → password_hash là placeholder không dùng tới.
Chạy: python -m app.scripts.seed  (sau alembic upgrade head)
"""

import asyncio

import sqlalchemy as sa

from app.stores.postgres import get_engine

GATEWAY_ID = "GW_S7200_01"


async def seed() -> None:
    async with get_engine().begin() as conn:
        gw = await conn.execute(
            sa.text(
                """
                INSERT INTO gateways (gateway_id, display_name, adapter_key)
                VALUES (:gid, :gname, 's7200_v1')
                ON CONFLICT (gateway_id) DO UPDATE SET updated_at = now()
                RETURNING id
                """
            ),
            {"gid": GATEWAY_ID, "gname": "Gateway S7-200 demo"},
        )
        gw_id = gw.scalar_one()

        await conn.execute(
            sa.text(
                """
                INSERT INTO slaves (gateway_id, slave_addr, name, protocol)
                VALUES (:gid, 1, 'S7-200', 'modbus-rtu')
                ON CONFLICT (gateway_id, slave_addr) DO NOTHING
                """
            ),
            {"gid": gw_id},
        )

        await conn.execute(
            sa.text(
                """
                INSERT INTO users (username, password_hash, role)
                VALUES ('admin', 'PLACEHOLDER-UNUSED-AUTH-PHASE-1', 'admin')
                ON CONFLICT (username) DO NOTHING
                """
            )
        )
    print(f"seed ok: gateway={GATEWAY_ID} id={gw_id}, slave 1, user admin")


if __name__ == "__main__":
    asyncio.run(seed())
