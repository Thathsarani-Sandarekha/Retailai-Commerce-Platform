"""Provider-selection checks; never contact a hosted API."""
from unittest.mock import MagicMock
import sys
from types import SimpleNamespace

from app.agents.agent import SingleAgent, SandboxModel, GroqModel, OpenAIModel


def test_groq_selected_with_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=lambda **kwargs: MagicMock(config=kwargs)))
    agent = SingleAgent()
    assert isinstance(agent.model, GroqModel)
    assert agent.model.mode == "groq"
    assert agent.model.model == "openai/gpt-oss-20b"
    assert agent.model.client.config["base_url"] == "https://api.groq.com/openai/v1"
    assert agent.model.client.config["api_key"] == "fake-test-key"


def test_groq_preferred_when_both_keys_exist(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-groq")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=lambda **kwargs: MagicMock()))
    assert SingleAgent().model.mode == "groq"


def test_no_key_uses_sandbox(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert isinstance(SingleAgent().model, SandboxModel)


def test_original_openai_mode_is_still_supported(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=lambda **kwargs: MagicMock()))
    assert isinstance(SingleAgent().model, OpenAIModel)
