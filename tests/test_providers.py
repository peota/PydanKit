"""The template must stay provider-agnostic: any MODEL_NAME should construct,
given that provider's key. We only check construction/wiring, never a real call.
"""

import pytest
from pydantic_ai import Agent


@pytest.mark.parametrize(
    ("model_name", "key_env"),
    [
        ("openai:gpt-4o", "OPENAI_API_KEY"),
        ("anthropic:claude-sonnet-4-5", "ANTHROPIC_API_KEY"),
        ("groq:llama-3.3-70b-versatile", "GROQ_API_KEY"),
        ("deepseek:deepseek-chat", "DEEPSEEK_API_KEY"),
    ],
)
def test_provider_model_constructs(monkeypatch, model_name, key_env):
    monkeypatch.setenv(key_env, "test-dummy-key")
    try:
        agent = Agent(model_name)
    except ImportError as exc:
        # The point is provider-agnostic wiring; whether an optional provider SDK
        # (e.g. `groq`) is installed is an environment concern, not a code regression.
        # The full `pydantic-ai` bundles most, but a clean clone may lack some.
        pytest.skip(f"{model_name}: provider SDK not installed ({exc})")
    assert agent is not None
