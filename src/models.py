"""Pydantic output models for structured agent responses."""

from pydantic import BaseModel, Field


class AgentResponse(BaseModel):
    """Example structured output - customize for your agent.

    Using structured outputs ensures the agent returns data in a
    predictable format that can be validated and processed reliably.

    Examples of custom response models:
        class AnalysisResponse(BaseModel):
            summary: str
            sentiment: Literal["positive", "negative", "neutral"]
            key_points: list[str]

        class CodeReviewResponse(BaseModel):
            issues: list[Issue]
            suggestions: list[str]
            approved: bool
    """

    content: str = Field(description="The main response content")
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional confidence score between 0 and 1",
    )
