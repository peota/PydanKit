"""Weather tools for the agent."""

from pydantic_ai import RunContext

from .dependencies import WeatherDeps


async def get_coordinates(ctx: RunContext[WeatherDeps], city: str) -> dict:
    """Get latitude and longitude for a city.

    Args:
        ctx: Run context with dependencies.
        city: City name to geocode.

    Returns:
        Dictionary with lat, lon, and full location name.
    """
    settings = ctx.deps.settings
    client = ctx.deps.http_client

    response = await client.get(
        settings.geocoding_url,
        params={"name": city, "count": 1, "language": "en", "format": "json"},
    )
    response.raise_for_status()
    data = response.json()

    if not data.get("results"):
        return {"error": f"City '{city}' not found"}

    result = data["results"][0]
    return {
        "latitude": result["latitude"],
        "longitude": result["longitude"],
        "name": result.get("name", city),
        "country": result.get("country", "Unknown"),
    }


async def get_weather(ctx: RunContext[WeatherDeps], city: str) -> dict:
    """Get current weather for a city.

    Args:
        ctx: Run context with dependencies.
        city: City name to get weather for.

    Returns:
        Dictionary with current weather data.
    """
    # First get coordinates
    coords = await get_coordinates(ctx, city)
    if "error" in coords:
        return coords

    settings = ctx.deps.settings
    client = ctx.deps.http_client

    # Determine temperature unit
    temp_unit = "fahrenheit" if settings.temperature_unit == "fahrenheit" else "celsius"

    response = await client.get(
        settings.weather_url,
        params={
            "latitude": coords["latitude"],
            "longitude": coords["longitude"],
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "temperature_unit": temp_unit,
            "wind_speed_unit": "kmh",
        },
    )
    response.raise_for_status()
    data = response.json()

    current = data.get("current", {})

    # Map weather codes to descriptions
    weather_code = current.get("weather_code", 0)
    conditions = _weather_code_to_description(weather_code)

    return {
        "location": f"{coords['name']}, {coords['country']}",
        "temperature": current.get("temperature_2m"),
        "temperature_unit": "F" if temp_unit == "fahrenheit" else "C",
        "humidity": current.get("relative_humidity_2m"),
        "wind_speed": current.get("wind_speed_10m"),
        "conditions": conditions,
    }


async def get_forecast(ctx: RunContext[WeatherDeps], city: str, days: int = 3) -> dict:
    """Get weather forecast for a city.

    Args:
        ctx: Run context with dependencies.
        city: City name to get forecast for.
        days: Number of days to forecast (1-7).

    Returns:
        Dictionary with forecast data.
    """
    # First get coordinates
    coords = await get_coordinates(ctx, city)
    if "error" in coords:
        return coords

    settings = ctx.deps.settings
    client = ctx.deps.http_client

    # Clamp days to valid range
    days = max(1, min(7, days))

    temp_unit = "fahrenheit" if settings.temperature_unit == "fahrenheit" else "celsius"

    response = await client.get(
        settings.weather_url,
        params={
            "latitude": coords["latitude"],
            "longitude": coords["longitude"],
            "daily": "temperature_2m_max,temperature_2m_min,weather_code",
            "temperature_unit": temp_unit,
            "forecast_days": days,
        },
    )
    response.raise_for_status()
    data = response.json()

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    max_temps = daily.get("temperature_2m_max", [])
    min_temps = daily.get("temperature_2m_min", [])
    weather_codes = daily.get("weather_code", [])

    forecast = []
    for i in range(len(dates)):
        forecast.append({
            "date": dates[i],
            "high": max_temps[i] if i < len(max_temps) else None,
            "low": min_temps[i] if i < len(min_temps) else None,
            "conditions": _weather_code_to_description(
                weather_codes[i] if i < len(weather_codes) else 0
            ),
        })

    return {
        "location": f"{coords['name']}, {coords['country']}",
        "temperature_unit": "F" if temp_unit == "fahrenheit" else "C",
        "forecast": forecast,
    }


def _weather_code_to_description(code: int) -> str:
    """Convert WMO weather code to human-readable description."""
    codes = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }
    return codes.get(code, "Unknown")
