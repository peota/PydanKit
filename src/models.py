"""Example structured-output model (opt-in).

By default the agent returns plain text (``output_type=str`` in ``agent.py``),
which keeps the skeleton minimal and makes streaming trivial.

When you want the LLM to return validated, machine-usable data instead of prose,
set an output model on the agent::

    from src.models import AgentResponse
    agent = Agent(..., output_type=AgentResponse)

The example below is intentionally *not* a single string field wrapped in an
object (that would add ceremony without value). It shows what structured output
is actually for: multiple typed fields, an enum, and a list the caller can rely
on without parsing free text. Replace it with a model that fits your use case.
"""

from typing import Literal

from pydantic import BaseModel, Field


class AgentResponse(BaseModel):
    """Example structured response. Customize the fields for your agent."""

    summary: str = Field(description="A short natural-language answer for the user")
    sentiment: Literal["positive", "neutral", "negative"] = Field(
        description="Overall sentiment the agent detected in the request"
    )
    key_points: list[str] = Field(
        default_factory=list,
        description="Salient points extracted from the answer, as discrete items",
    )
