"""应用配置：统一从环境变量 / .env 读取。

原则：配置只在这里出现一次，其它模块通过 ``get_settings()`` 获取，
不要在业务代码里散落 ``os.getenv``。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "independent-site-integration-service"
    environment: str = "local"

    database_url: str = (
        "mysql+pymysql://app:app_pass@127.0.0.1:3306/shopify_shopline?charset=utf8mb4"
    )
    redis_url: str = "redis://:redis_pass@127.0.0.1:6379/0"

    # 租约必须明显大于单次任务的最长执行时间，否则会出现"任务还在跑、租约已经过期"。
    lease_seconds: int = 20
    lease_grace_seconds: int = 2

    webhook_secret: str = "dev_secret"
    max_attempts: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
