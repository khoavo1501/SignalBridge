from dataclasses import dataclass

from app.config import get_settings


@dataclass
class User:
    username: str
    role: str


async def get_current_user() -> User:
    # AUTH_ENABLED=false ở phase 1: stub trả user admin giả (PROJECT_PLAN.md §4.5).
    # Khi bật auth: thay bằng JWT/session, giữ nguyên signature để không đổi handler.
    if get_settings().auth_enabled:
        raise NotImplementedError("Auth sẽ được implement sau phase 1")
    return User(username="dev-admin", role="admin")
