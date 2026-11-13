from __future__ import annotations

from app.config import get_settings


def test_settings_load() -> None:
    settings = get_settings()
    assert settings.app_name == "independent-site-integration-service"
    assert settings.lease_seconds > settings.lease_grace_seconds
    assert settings.database_url.startswith("mysql+pymysql://")


def test_settings_are_cached() -> None:
    assert get_settings() is get_settings()
