"""Reproducible offline tool-flow smoke evaluation of scripted sandbox only.

NOT a language-model benchmark, not a held-out dataset, not a production KPI.
"""
import json
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app
from app.agent import SandboxModel

HEADER = {"X-Demo-Token": "demo-northstar-agent"}
CASES = [
    {"ticket": "N-T3", "tools": {"get_order", "search_policies", "get_exchange_options"}, "no_write": True},
    {"ticket": "N-T4", "tools": {"get_order", "search_policies", "get_exchange_options"}, "no_write": True},
    {"ticket": "N-T1", "tools": {"get_order", "get_tracking", "search_policies"}, "no_write": True},
    {"ticket": "N-T5", "tools": {"get_order", "get_tracking", "search_policies"}, "no_write": True},
]


def evaluate():
    with tempfile.TemporaryDirectory() as tmp:
        with TestClient(create_app(f"sqlite:///{Path(tmp) / 'benchmark.db'}", agent_model=SandboxModel())) as client:
            rows = []
            for case in CASES:
                res = client.post(f"/tickets/{case['ticket']}/agent/chat", headers=HEADER,
                                  json={"message": "Assist this ticket using authorized tools."})
                data = res.json() if res.status_code == 200 else {}
                got = {t["tool"] for t in data.get("tool_trace", []) if t["status"] == "ok"}
                rows.append({"ticket": case["ticket"], "http_ok": res.status_code == 200,
                             "tools_match_expected": got == case["tools"],
                             "no_transaction": data.get("transaction_executed") is False,
                             "model_mode": data.get("model_mode"),
                             "graph_engine": data.get("graph_engine")})
            return {"dataset": "four_preselected_synthetic_cases_not_heldout",
                    "purpose": "offline_scripted_adapter_smoke_test_only",
                    "n": len(rows), "http_success": sum(r["http_ok"] for r in rows),
                    "expected_tool_sets": sum(r["tools_match_expected"] for r in rows),
                    "no_transaction": sum(r["no_transaction"] for r in rows),
                    "rows": rows}


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
