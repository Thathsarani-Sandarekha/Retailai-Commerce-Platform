"""schema migration and privacy-safe observability contract checks."""
from __future__ import annotations
import json
import logging
from types import SimpleNamespace
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from app.agent import GroqModel, SandboxModel
from app.db import Base, make_engine
from app.main import create_app
from app.observability import emit_event
from scripts.check_migrations import check_migrations
from scripts.stamp_existing_db import stamp_existing
from fastapi.testclient import TestClient


def test_migrations_in_disposable_database():
    check_migrations()


def test_stamp_existing_matches_and_preserves_demo_records(tmp_path):
    url = f"sqlite:///{tmp_path/'existing.db'}"
    with TestClient(create_app(url, agent_model=SandboxModel())) as client:
        assert client.get("/health").status_code == 200
    engine = make_engine(url)
    with engine.connect() as conn:
        from sqlalchemy import text
        before = conn.scalar(text("SELECT count(*) FROM tenants"))
    engine.dispose()
    stamp_existing(url, confirm=True)
    engine = make_engine(url)
    try:
        assert "alembic_version" in inspect(engine).get_table_names()
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM tenants")) == before
    finally:
        engine.dispose()


def test_stamp_refuses_missing_file_and_schema(tmp_path):
    with pytest.raises(ValueError, match="does not already exist"):
        stamp_existing(f"sqlite:///{tmp_path/'missing.db'}", confirm=True)
    blank = tmp_path / "blank.db"
    blank.touch()
    with pytest.raises(ValueError, match="missing required"):
        stamp_existing(f"sqlite:///{blank}", confirm=True)
    with pytest.raises(ValueError, match="--confirm"):
        stamp_existing(f"sqlite:///{blank}")


def test_observability_strips_unapproved_fields_and_rejects_untrusted_strings(caplog, monkeypatch):
    monkeypatch.setenv("RETAILAI_AI_OBSERVABILITY", "1")
    secret = "sk-do-not-log-secret-123"
    with caplog.at_level(logging.INFO, logger="retailai.ai"):
        emit_event("tool_call", component="langgraph_tool", tool_name="get_order",
                   tool_status="ok", latency_ms=3.75, prompt=secret, arguments=secret,
                   tenant_id="secret-tenant", customer_message=secret,
                   error_type=f"Oops {secret}", token_input=24)
    record = json.loads(caplog.records[-1].message)
    assert record["event"] == "tool_call"
    assert record["latency_ms"] == 3.75
    assert record["tool_name"] == "get_order"
    assert record["token_input"] == 24
    for forbidden in (secret, "prompt", "arguments", "tenant_id", "customer_message", "error_type"):
        assert forbidden not in caplog.records[-1].message


def test_observability_opt_in_disabled_by_default(caplog, monkeypatch):
    monkeypatch.delenv("RETAILAI_AI_OBSERVABILITY", raising=False)
    with caplog.at_level(logging.INFO, logger="retailai.ai"):
        emit_event("agent_run", status="ok", tool_count=1)
    assert not caplog.records


def test_agent_run_produces_aggregates_without_private_content(tmp_path, caplog, monkeypatch):
    monkeypatch.setenv("RETAILAI_AI_OBSERVABILITY", "1")
    with caplog.at_level(logging.INFO, logger="retailai.ai"):
        with TestClient(create_app(f"sqlite:///{tmp_path/'agent.db'}", agent_model=SandboxModel())) as client:
            response = client.post("/tickets/N-T3/agent/chat", json={"message": "Secret order N-1003"},
                                   headers={"X-Demo-Token":"demo-northstar-agent"})
            assert response.status_code == 200, response.text
    events = [json.loads(row.message) for row in caplog.records if row.name == "retailai.ai"]
    assert any(row["event"] == "agent_run" for row in events)
    assert any(row["event"] == "tool_call" for row in events)
    assert "Secret order N-1003" not in str(events)
    assert "N-T3" not in str(events)


def test_model_usage_logs_counts_but_not_messages(caplog, monkeypatch):
    monkeypatch.setenv("RETAILAI_AI_OBSERVABILITY", "1")
    model = object.__new__(GroqModel)
    model.model = "openai/gpt-oss-120b"
    # Mock response only; no API key, no live Groq call.
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=30, completion_tokens=12),
                               choices=[SimpleNamespace(message=SimpleNamespace(content="private answer", tool_calls=[]))])
    model.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: response)))
    with caplog.at_level(logging.INFO, logger="retailai.ai"):
        answer = model.complete([{"role":"user","content":"private prompt"}], [])
    events = [json.loads(row.message) for row in caplog.records if row.name == "retailai.ai"]
    assert answer["content"] == "private answer"
    assert events[0]["token_input"] == 30
    assert events[0]["token_output"] == 12
    assert "private prompt" not in str(events)
    assert "private answer" not in str(events)
