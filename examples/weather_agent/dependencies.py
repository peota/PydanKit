"""Dependencies for the weather agent."""

from dataclasses import dataclass, field

import httpx

from .config import WeatherSettings, get_settings


@dataclass
class WeatherDeps:
    """Dependencies injected into weather agent tools.

    Attributes:
        http_client: Async HTTP client for API calls.
        settings: Weather agent settings.
    """

    http_client: httpx.AsyncClient = field(default_factory=httpx.AsyncClient)
    settings: WeatherSettings = field(default_factory=get_settings)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.http_client.aclose()
