"""Privacy-first, structured AI telemetry for stdout / container log collection.

No prompts, replies, tool arguments, IDs, photos, tokens, or API keys are logged.
The logger is intentionally sink-agnostic: it works locally, in Docker, and in
CloudWatch when ECS captures container stdout. No external tracing is implied.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone

LOGGER = logging.getLogger("retailai.ai")
_ALLOWED_EVENTS = {"ai_model_completion", "tool_call", "agent_run", "vision_inference"}
_ALLOWED_KEYS = {"component", "status", "model_mode", "model_name", "graph_engine",
                 "tool_name", "tool_status", "latency_ms", "steps", "tool_count",
                 "blocked_tools", "token_input", "token_output", "error_type"}
_TEXT_KEYS = {"component", "status", "model_mode", "model_name", "graph_engine",
              "tool_name", "tool_status", "error_type"}
_NUMBER_KEYS = _ALLOWED_KEYS - _TEXT_KEYS
_SAFE_TEXT = re.compile(r"^[A-Za-z0-9_./:-]{1,80}$")


def emit_event(event: str, **attributes: object) -> None:
    """Emit allowlisted metric fields only; never serialize arbitrary input."""
    if os.getenv("RETAILAI_AI_OBSERVABILITY", "0").lower() not in ("1", "true", "yes"):
        return
    record: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event if event in _ALLOWED_EVENTS else "unknown",
    }
    for name, value in attributes.items():
        if name not in _ALLOWED_KEYS or value is None or isinstance(value, bool):
            continue
        if name in _TEXT_KEYS and isinstance(value, str) and _SAFE_TEXT.fullmatch(value):
            record[name] = value
        elif name in _NUMBER_KEYS and isinstance(value, (int, float)) and 0 <= value <= 1e12:
            record[name] = round(value, 2) if isinstance(value, float) else value
    LOGGER.info(json.dumps(record, separators=(",", ":"), ensure_ascii=True))
