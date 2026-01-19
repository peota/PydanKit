"""Configuration settings for the weather agent."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class WeatherSettings(BaseSettings):
    """Weather agent configuration."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM Configuration
    model_name: str = "openai:gpt-4o-mini"
    openai_api_key: str = ""

    # Observability
    logfire_token: str | None = None

    # Debug
    debug: bool = False

    # Weather API settings (Open-Meteo is free, no key required)
    geocoding_url: str = "https://geocoding-api.open-meteo.com/v1/search"
    weather_url: str = "https://api.open-meteo.com/v1/forecast"

    # Display settings
    temperature_unit: str = "celsius"  # celsius or fahrenheit


def get_settings() -> WeatherSettings:
    """Get application settings (cached)."""
    return WeatherSettings()
