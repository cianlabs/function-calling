"""Tests for weather helpers. These do not call the network."""

import pytest

from weather import (
    BAD_TOOL_ARGUMENTS,
    CITY_NOT_FOUND,
    TOOL_NOT_FOUND,
    call_tool,
    condition_from_code,
    get_weather,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail if a test reaches httpx.get without supplying its own mock."""

    def refuse(*args, **kwargs):
        raise RuntimeError("tests must not use the network")

    monkeypatch.setattr("weather.httpx.get", refuse)


@pytest.mark.parametrize(
    ("code", "condition"),
    [
        (0, "Clear"),
        (1, "Partly cloudy"),
        (3, "Partly cloudy"),
        (45, "Fog"),
        (48, "Fog"),
        (51, "Rain"),
        (67, "Rain"),
        (71, "Snow"),
        (77, "Snow"),
        (80, "Showers"),
        (82, "Showers"),
        (95, "Thunderstorm"),
        (99, "Thunderstorm"),
    ],
)
def test_condition_from_code(code, condition):
    assert condition_from_code(code) == condition


def test_city_not_found(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": []}

    def fake_get(url, params=None, timeout=None):
        assert url == "https://geocoding-api.open-meteo.com/v1/search"
        assert params == {"name": "Atlantis", "count": 1}
        assert timeout == 10
        return Response()

    monkeypatch.setattr("weather.httpx.get", fake_get)

    with pytest.raises(CITY_NOT_FOUND) as raised:
        get_weather("Atlantis")

    message = str(raised.value)
    assert "Atlantis" in message
    assert "Check the spelling" in message


def test_tool_not_found():
    with pytest.raises(TOOL_NOT_FOUND) as raised:
        call_tool("get_forecast", '{"city": "Tokyo"}')
    message = str(raised.value)
    assert "get_forecast" in message
    assert "get_weather" in message


def test_bad_tool_arguments_invalid_json():
    with pytest.raises(BAD_TOOL_ARGUMENTS) as raised:
        call_tool("get_weather", "{")
    message = str(raised.value)
    assert "not valid JSON" in message
    assert "city" in message


def test_bad_tool_arguments_missing_city():
    with pytest.raises(BAD_TOOL_ARGUMENTS) as raised:
        call_tool("get_weather", '{"units": "c"}')
    message = str(raised.value)
    assert "missing city" in message
