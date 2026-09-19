from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_topic_filter: str = "devices/+/+"

    database_url: str = "postgresql+asyncpg://sb:sb@localhost:5432/signalbridge"
    influx_url: str = "http://localhost:8086"
    influx_token: str = ""
    influx_org: str = "signalbridge"
    influx_bucket: str = "plc"
    redis_url: str = "redis://localhost:6379/0"

    stale_threshold_s: int = 10
    ws_telemetry_min_interval_ms: int = 250
    auth_enabled: bool = False
    ingest_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
