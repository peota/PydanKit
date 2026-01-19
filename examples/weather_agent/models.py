"""Output models for the weather agent."""

from pydantic import BaseModel, Field


class WeatherResponse(BaseModel):
    """Structured weather response from the agent.

    This model constrains the agent's output to a consistent format.
    """

    location: str = Field(description="The city and country")
    temperature: float = Field(description="Current temperature")
    temperature_unit: str = Field(description="Temperature unit (C or F)")
    conditions: str = Field(description="Weather conditions description")
    humidity: int | None = Field(default=None, description="Humidity percentage")
    wind_speed: float | None = Field(default=None, description="Wind speed in km/h")
    summary: str = Field(description="Human-friendly weather summary")
