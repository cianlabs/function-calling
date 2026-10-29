"""Ask a Grok model (xAI) for the weather in Tokyo, using a get_weather tool."""

import json
import os
import sys

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

# Open-Meteo: free weather data, no API key needed.
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_TIMEOUT_SECONDS = 10


class Failure(Exception):
    """A known failure. main() prints one line and exits."""


class MISSING_KEY(Failure):
    def __init__(self) -> None:
        super().__init__(
            "XAI_API_KEY is not set. Set that environment variable to your xAI API key and run the script again."
        )


class BAD_REQUEST(Failure):
    def __init__(self, server_message: str) -> None:
        super().__init__(
            "The API rejected the request (HTTP 400): "
            f"{server_message}. Correct the request and try again."
        )


class RATE_LIMITED_OR_NO_CREDIT(Failure):
    def __init__(self) -> None:
        super().__init__(
            "The API returned HTTP 429 because the account is rate limited or out of credit. "
            "Wait and try again, or add credit to the xAI account."
        )


class UNREACHABLE(Failure):
    def __init__(self) -> None:
        super().__init__(
            "The API could not be reached because the connection failed or the request timed out. "
            "Check the network and try again."
        )


class TOOL_NOT_FOUND(Failure):
    def __init__(self, name: str) -> None:
        super().__init__(
            f"The model asked for the tool {name!r}, which this script does not have. "
            "Call get_weather, or add a handler for that tool."
        )


class BAD_TOOL_ARGUMENTS(Failure):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class CITY_NOT_FOUND(Failure):
    def __init__(self, city: str) -> None:
        super().__init__(
            f"No place called {city!r} was found. Check the spelling or try a bigger nearby city."
        )


class WEATHER_UNREACHABLE(Failure):
    def __init__(self) -> None:
        super().__init__(
            "The weather service (Open-Meteo) could not be reached or took too long. "
            "Check the network and try again."
        )


class WEATHER_BAD_ANSWER(Failure):
    def __init__(self) -> None:
        super().__init__(
            "The weather service answered in a shape this script does not understand. "
            "Try again later."
        )


def condition_from_code(code: int) -> str:
    """Turn an Open-Meteo weather code into a short plain-English condition."""
    if code == 0:
        return "Clear"
    if 1 <= code <= 3:
        return "Partly cloudy"
    if 45 <= code <= 48:
        return "Fog"
    if 51 <= code <= 67:
        return "Rain"
    if 71 <= code <= 77:
        return "Snow"
    if 80 <= code <= 82:
        return "Showers"
    if 95 <= code <= 99:
        return "Thunderstorm"
    return "Unknown"


def _get_json(url: str, params: dict) -> dict:
    try:
        response = httpx.get(url, params=params, timeout=WEATHER_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except (httpx.TimeoutException, httpx.NetworkError):
        raise WEATHER_UNREACHABLE() from None
    except (httpx.HTTPError, ValueError):
        raise WEATHER_BAD_ANSWER() from None
    if not isinstance(data, dict):
        raise WEATHER_BAD_ANSWER()
    return data


def get_weather(city: str) -> str:
    """Return the current weather for a city, using Open-Meteo."""
    geo = _get_json(GEOCODING_URL, {"name": city.strip(), "count": 1})
    results = geo.get("results") if isinstance(geo, dict) else None
    if not results:
        raise CITY_NOT_FOUND(city)
    try:
        place = results[0]
        latitude, longitude = place["latitude"], place["longitude"]
        found_name = place.get("name", city)
    except (KeyError, TypeError, IndexError):
        raise WEATHER_BAD_ANSWER() from None

    forecast = _get_json(
        FORECAST_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min,weather_code",
            "forecast_days": 7,
            "timezone": "auto",
        },
    )
    try:
        current = forecast["current"]
        temperature = current["temperature_2m"]
        code = int(current["weather_code"])
        daily = forecast["daily"]
        days = [
            {
                "date": date,
                "high_c": high,
                "low_c": low,
                "condition": condition_from_code(int(day_code)),
            }
            for date, high, low, day_code in zip(
                daily["time"],
                daily["temperature_2m_max"],
                daily["temperature_2m_min"],
                daily["weather_code"],
            )
        ]
    except (KeyError, TypeError, ValueError):
        raise WEATHER_BAD_ANSWER() from None

    return json.dumps(
        {
            "city": found_name,
            "temperature_c": temperature,
            "condition": condition_from_code(code),
            "forecast": days,
        }
    )


def format_forecast(result: str) -> str:
    """Turn get_weather's JSON into a readable, one-line-per-day forecast."""
    report = json.loads(result)
    lines = [f"{report['city']}: now {report['temperature_c']}°C, {report['condition']}"]
    for day in report.get("forecast", []):
        lines.append(
            f"  {day['date']}  low {day['low_c']}°C  high {day['high_c']}°C  {day['condition']}"
        )
    return "\n".join(lines)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather and a 7-day forecast (daily high, low and condition) for a city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name, for example Tokyo.",
                    }
                },
                "required": ["city"],
            },
        },
    }
]


def _redact(text: str) -> str:
    raw = os.environ.get("XAI_API_KEY") or ""
    for key in {raw, raw.strip()}:
        if key:
            text = text.replace(key, "[redacted]")
    return text


def call_tool(name: str, arguments: str) -> str:
    """Run a model tool call, or raise TOOL_NOT_FOUND / BAD_TOOL_ARGUMENTS."""
    if name != "get_weather":
        raise TOOL_NOT_FOUND(name)
    try:
        args = json.loads(arguments)
    except (TypeError, json.JSONDecodeError):
        raise BAD_TOOL_ARGUMENTS(
            "The tool arguments are not valid JSON. "
            "Send a JSON object that includes a city name and try again."
        )
    city = args.get("city") if isinstance(args, dict) else None
    if not isinstance(city, str) or not city.strip():
        raise BAD_TOOL_ARGUMENTS(
            "The tool arguments are missing city. Include a city name and try again."
        )
    return get_weather(city)


def _server_message(exc: APIStatusError) -> str:
    message = ""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict):
            message = str(error.get("message") or "")
        elif isinstance(error, str):
            message = error
    elif isinstance(body, str):
        message = body
    if not message:
        message = str(getattr(exc, "message", "") or "")
        prefix = f"Error code: {exc.status_code} - "
        if message.startswith(prefix):
            message = message[len(prefix) :]
        elif message == f"Error code: {exc.status_code}":
            message = ""
    message = " ".join(message.split())
    return _redact(message) or "the server did not include a message"


def _complete(client: OpenAI, **kwargs):
    try:
        return client.chat.completions.create(**kwargs)
    except APIStatusError as exc:
        if exc.status_code == 400:
            raise BAD_REQUEST(_server_message(exc)) from None
        if exc.status_code == 429:
            raise RATE_LIMITED_OR_NO_CREDIT() from None
        raise
    except (APITimeoutError, APIConnectionError):
        raise UNREACHABLE() from None


def main() -> None:
    try:
        key = (os.environ.get("XAI_API_KEY") or "").strip()
        if not key:
            raise MISSING_KEY()

        client = OpenAI(api_key=key, base_url="https://api.x.ai/v1")
        model = os.environ.get("XAI_MODEL", "grok-build-0.1")  # if this fails, try "grok-3"
        messages = [{"role": "user", "content": "What's the weather forecast for the next several days in Reykjavik, Iceland?"}]

        response = _complete(client, model=model, messages=messages, tools=TOOLS)
        message = response.choices[0].message
        messages.append(message)

        for call in message.tool_calls or []:
            result = _redact(call_tool(call.function.name, call.function.arguments))
            args = json.loads(call.function.arguments)
            print(f"get_weather({args}) returned:")
            print(_redact(format_forecast(result)))
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

        if message.tool_calls:
            response = _complete(client, model=model, messages=messages, tools=TOOLS)
            message = response.choices[0].message

        content = message.content
        if isinstance(content, str):
            content = _redact(content)
        print(content)
    except Failure as failure:
        print(f"{type(failure).__name__}: {_redact(str(failure))}")
        sys.exit(1)


if __name__ == "__main__":
    main()
