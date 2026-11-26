"""Privacy-safe telemetry demo. Does not call an AI service or connect to a DB."""
from __future__ import annotations
import logging
import os
from app.observability import emit_event


def demo_observability() -> None:
    os.environ["RETAILAI_AI_OBSERVABILITY"] = "1"
    logging.basicConfig(format="%(message)s", level=logging.INFO)
    emit_event("ai_model_completion", component="chat_model", model_mode="groq",
               model_name="openai/gpt-oss-120b", status="ok", latency_ms=121.67,
               token_input=68, token_output=21,
               secret="DO_NOT_LOG", prompt="DO_NOT_LOG")
    emit_event("tool_call", component="langgraph_tool", tool_name="search_retail_products",
               tool_status="ok", latency_ms=3.28, arguments="DO_NOT_LOG")
    emit_event("agent_run", component="langgraph_agent", model_mode="groq",
               graph_engine="langgraph", status="ok", latency_ms=174.23,
               steps=2, tool_count=1, blocked_tools=0)
    print("RetailAI AI observability smoke: PASS")
    print("Structured safe metrics emitted; sample only; no LLM, DB or AWS calls")


if __name__ == "__main__":
    demo_observability()
