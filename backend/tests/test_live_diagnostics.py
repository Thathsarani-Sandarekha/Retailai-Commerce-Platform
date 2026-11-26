"""No live provider calls: verify sanitized failure attribution using a fake 429."""
import json
from scripts import evaluate_retailai as ev


def test_safe_provider_diagnostics_drop_private_text():
    class ProviderError(Exception):
        status_code = 429
        body = {"error": {"code": "rate_limit_exceeded", "message": "private message sk-test-secret"}}
    data = ev.sanitized_provider_failure(ProviderError("sk-test-secret"))
    assert data == {
        "category": "provider_rate_limit",
        "exception_class": "ProviderError",
        "provider_http_status": 429,
        "provider_error_code": "rate_limit_exceeded",
    }
    assert "sk-test-secret" not in json.dumps(data)


def test_failed_live_request_is_diagnostic_not_model_accuracy(monkeypatch):
    class FakeGroqModel:
        mode = "groq"
        def complete(self, messages, tools):
            class FakeLimitError(Exception):
                status_code = 429
                body = {"error": {"code": "rate_limit_exceeded", "message": "private"}}
            raise FakeLimitError("private")

    monkeypatch.setattr(ev, "GroqModel", FakeGroqModel)
    dataset = json.loads(ev.DATASET.read_text(encoding="utf-8"))
    result = ev.evaluate_agent_cases(dataset, "groq", 1)
    row = result["records"][0]
    assert row["http_status"] == 503  # API intentionally masks provider internals
    assert row["provider_failure"]["provider_http_status"] == 429
    assert row["provider_failure"]["category"] == "provider_rate_limit"
    assert not row["success_http"]
    assert result["tool_call_success_rate"] is None
    assert result["latency_p50_ms"] is None
    report = ev.to_markdown({
        "mode": "opt_in_live_groq_inference",
        "dataset_id": "diagnostic-test",
        "agent_tool_paths": result,
        "rule_based_intent_baseline": {"n": 1, "macro_f1": 0.0},
        "deterministic_business_contracts": {"passed": 1, "n": 1},
        "hostile_model_safety_probe": {"passed": 1, "n": 1},
        "limitations": ["diagnostic only"],
    })
    assert "Failed Groq requests" in report
    assert "provider_rate_limit" in report
    assert "private" not in report
