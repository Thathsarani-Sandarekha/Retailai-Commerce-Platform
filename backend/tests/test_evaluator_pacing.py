"""metrics are scoped to completed requests; don't hammer 429."""
import json

import pytest

from scripts import evaluate_retailai as ev


def test_select_named_scenario_without_touching_other_cases():
    dataset = json.loads(ev.DATASET.read_text(encoding="utf-8"))
    chosen = ev.choose_agent_cases(dataset, ["read_cart"])
    assert [c["id"] for c in chosen] == ["read_cart"]
    assert [c["id"] for c in ev.choose_agent_cases(dataset, ["read_cart", "exchange_leggings"])] == [
        "exchange_leggings", "read_cart"]
    with pytest.raises(ValueError, match="Unknown case IDs"):
        ev.choose_agent_cases(dataset, ["not-a-real-scenario"])


def test_success_only_tool_accuracy_does_not_count_429_as_a_model_trial():
    base = dict(attempted_tool_calls=2, successful_tool_calls=2,
                no_unauthorized_business_mutation=True, nonempty_response=True, latency_ms=123.4)
    records = [
        {**base, "case_id": "success", "success_http": True, "tool_set_exact": True},
        {**base, "case_id": "failure", "success_http": False, "tool_set_exact": False,
         "attempted_tool_calls": 0, "successful_tool_calls": 0, "latency_ms": 600.0},
    ]
    stats = ev.summarize_tool_records(records, planned_n=8)
    assert stats["tool_set_accuracy"] == 0.5  # legacy attempted-case metric
    assert stats["tool_set_accuracy_success_only"] == 1.0
    assert stats["successful_cases"] == 1
    assert stats["planned_n"] == 8
    assert stats["latency_p50_ms"] == 123.4


def test_429_short_circuits_remaining_cases_without_new_provider_calls(monkeypatch):
    class RateLimited(Exception):
        status_code = 429
        body = {"error": {"code": "rate_limit_exceeded"}}

    class FakeGroqModel:
        def __init__(self):
            pass

        def complete(self, *_):
            raise RateLimited("Never include raw provider body in output")

    monkeypatch.setattr(ev, "GroqModel", FakeGroqModel)
    dataset = json.loads(ev.DATASET.read_text(encoding="utf-8"))
    result = ev.evaluate_agent_cases(dataset, "groq", None, delay_seconds=0)
    assert result["n"] == 1
    assert result["planned_n"] == 8
    assert result["stopped_on_rate_limit"] is True
    assert result["records"][0]["provider_failure"]["category"] == "provider_rate_limit"
    assert result["tool_set_accuracy_success_only"] is None


def test_offline_named_case_succeeds_and_does_not_wait(monkeypatch):
    def unexpected_sleep(seconds):
        raise AssertionError(f"Offline evaluator unexpectedly waited {seconds}s")

    monkeypatch.setattr(ev.time, "sleep", unexpected_sleep)
    dataset = json.loads(ev.DATASET.read_text(encoding="utf-8"))
    result = ev.evaluate_agent_cases(dataset, "offline", None, case_ids=["read_cart"])
    assert result["n"] == 1
    assert result["planned_n"] == 1
    assert result["tool_set_accuracy_success_only"] == 1.0
    assert result["records"][0]["observed_tools"] == ["get_my_cart"]


def test_report_lists_tool_mismatches_without_raw_prompts():
    record = dict(case_id="some_scenario", success_http=True,
                  expected_tools=["get_order", "search_policies"],
                  observed_tools=["get_order", "get_order"],
                  missing_expected_tools=["search_policies"],
                  unexpected_tools=[], repeated_tools=["get_order"], tool_set_exact=False)
    report = {
        "mode": "opt_in_live_groq_inference",
        "dataset_id": "synthetic", "agent_tool_paths": {
            "n": 1, "planned_n": 1, "successful_cases": 1,
            "tool_set_accuracy": 0, "tool_set_accuracy_success_only": 0,
            "tool_call_success_rate": 1, "no_unauthorized_mutations_rate": 1,
            "http_success_rate": 1, "latency_p50_ms": 2, "latency_p95_ms": 2,
            "records": [record], "stopped_on_rate_limit": False,
        },
        "rule_based_intent_baseline": {"n": 1, "macro_f1": 1},
        "deterministic_business_contracts": {"passed": 1, "n": 1},
        "hostile_model_safety_probe": {"passed": 1, "n": 1},
        "limitations": ["synthetic"],
    }
    md = ev.to_markdown(report)
    assert "Successful case tool diagnostics" in md
    assert "search_policies" in md
    assert "get_order, get_order" in md
    assert "Some sensitive prompt text" not in md
