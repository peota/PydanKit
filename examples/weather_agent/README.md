# Weather Agent Example

A demonstration of PydanKit patterns using a weather API integration with [Open-Meteo](https://open-meteo.com/) (free, no API key required).

## Features Demonstrated

- **Custom Dependencies:** HTTP client injection via `WeatherDeps`
- **Custom Tools:** `get_weather(city)` and `get_forecast(city, days)`
- **Custom Output Model:** `WeatherResponse` with structured fields
- **External API Integration:** Open-Meteo geocoding and weather APIs

## Installation

```bash
# From the repository root
pip install -e "."

# Install httpx for HTTP requests
pip install httpx
```

## Usage

### CLI

```bash
# Single query
python -m examples.weather_agent.main chat "What's the weather in Tokyo?"

# Interactive mode
python -m examples.weather_agent.main interactive
```

### REST API with Dashboard

```bash
# Start the server (default: http://localhost:8001)
python -m examples.weather_agent.main serve

# With custom host/port
python -m examples.weather_agent.main serve --host 0.0.0.0 --port 8080
```

Open http://localhost:8001 in your browser to access the dashboard.

**API Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Dashboard UI |
| GET | `/health` | Health check |
| GET | `/info` | Agent info (model, tools) |
| POST | `/weather` | Send weather query |

**Example API request:**
```bash
curl -X POST http://localhost:8001/weather \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the weather in Paris?"}'
```

## Configuration

Create a `.env` file in the repository root:

```bash
OPENAI_API_KEY=sk-your-key-here

# Optional: change temperature unit (celsius or fahrenheit)
TEMPERATURE_UNIT=celsius
```

## Project Structure

```
examples/weather_agent/
├── __init__.py       # Package marker
├── config.py         # Settings (API URLs, units)
├── dependencies.py   # WeatherDeps with httpx client
├── models.py         # WeatherResponse output model
├── tools.py          # get_weather, get_forecast tools
├── agent.py          # Agent definition
├── api.py            # FastAPI server
├── main.py           # CLI entry point
├── static/
│   └── index.html    # Dashboard UI
└── README.md         # This file
```

## How It Works

1. **User Query:** User asks "What's the weather in London?"

2. **Agent Processing:** The agent decides to use the `get_weather` tool

3. **Tool Execution:**
   - Geocode "London" to get coordinates via Open-Meteo Geocoding API
   - Fetch weather data from Open-Meteo Weather API
   - Return structured data to the agent

4. **Response:** Agent formats the data into a `WeatherResponse` with location, temperature, conditions, and a friendly summary

## Extending This Example

### Add a new tool

```python
# In tools.py
async def get_air_quality(ctx: RunContext[WeatherDeps], city: str) -> dict:
    """Get air quality index for a city."""
    # Implementation here
    pass

# In agent.py
from .tools import get_air_quality
_agent.tool(get_air_quality)
```

### Modify the output model

```python
# In models.py
class WeatherResponse(BaseModel):
    # ... existing fields ...
    air_quality_index: int | None = Field(default=None, description="AQI value")
    uv_index: float | None = Field(default=None, description="UV index")
```

## API Reference

### Open-Meteo (No API key required)

- **Geocoding:** `https://geocoding-api.open-meteo.com/v1/search`
- **Weather:** `https://api.open-meteo.com/v1/forecast`

See [Open-Meteo Documentation](https://open-meteo.com/en/docs) for more options.
