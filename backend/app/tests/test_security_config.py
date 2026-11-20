import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.core.database import normalize_database_url
from app.core.exceptions import require_internal_token
from app.services.source_service import derive_state


def test_production_rejects_weak_token_and_wildcard_cors():
    probs = Settings(app_env="production", internal_api_token="change-me", cors_origins="*").security_problems()
    assert len(probs) == 2
    assert Settings(app_env="production", internal_api_token="x" * 24, cors_origins="https://app.example.com").security_problems() == []


def test_internal_token_constant_time_check(monkeypatch):
    monkeypatch.setattr("app.core.exceptions.get_settings", lambda: Settings(internal_api_token="s" * 20))
    require_internal_token("s" * 20)
    with pytest.raises(HTTPException) as e:
        require_internal_token("wrong")
    assert e.value.status_code == 401


@pytest.mark.parametrize(
    "raw,needle",
    [
        ("postgres://u:p@db.abc.supabase.co:5432/postgres", "postgresql+psycopg2://"),
        ("postgresql+asyncpg://u:p@h/db", "postgresql+psycopg2://"),
        ("postgresql://u:p@aws-0.pooler.supabase.com:6543/postgres", "sslmode=require"),
    ],
)
def test_database_url_normalisation(raw, needle):
    assert needle in normalize_database_url(raw)


def test_connector_state_derived_from_facts():
    assert derive_state(False, "ok") == "unavailable"
    assert derive_state(True, None) == "configured"      # configured is never "operational"
    assert derive_state(True, "ok") == "operational"
    assert derive_state(True, "quota") == "failing"
    assert derive_state(True, "error") == "failing"
