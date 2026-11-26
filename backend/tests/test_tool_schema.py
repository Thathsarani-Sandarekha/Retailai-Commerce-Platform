"""Regression checks for Groq/OpenAI strict function-tool schemas.

These tests do not call Groq and are not evidence of live-model accuracy.
"""

from app.agents.agent import TOOL_SCHEMAS, openai_tool_specs
from app.styling.styling import ThreeLooksRequest


def test_every_strict_tool_has_all_properties_required():
    tools = openai_tool_specs()
    assert len(tools) == len(TOOL_SCHEMAS)
    for tool in tools:
        function = tool["function"]
        assert function["strict"] is True, function["name"]
        schema = function["parameters"]
        assert schema["type"] == "object", function["name"]
        assert schema.get("additionalProperties") is False, function["name"]
        assert set(schema.get("required", [])) == set(schema.get("properties", {})), function["name"]
        assert all("default" not in v for v in schema.get("properties", {}).values()), function["name"]


def test_three_looks_tool_requires_explicit_already_owned_without_changing_customer_endpoint():
    function = next(t["function"] for t in openai_tool_specs() if t["function"]["name"] == "build_three_looks")
    assert "already_owned" in function["parameters"]["required"]
    # Direct customer API remains backward compatible with omitted flag.
    direct = ThreeLooksRequest.model_validate({
        "anchor_variant_id": "N-V-JEANS-28", "budget_cents": 25000,
        "clothing_size": "M", "shoe_size": "US 8", "denim_size": "28",
    })
    assert direct.already_owned is False
