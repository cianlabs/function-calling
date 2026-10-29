"""Tests for weather helpers. These do not call the network."""

import json

import pytest

from weather import (
    BAD_TOOL_ARGUMENTS,
    CITY_NOT_FOUND,
    TOOL_NOT_FOUND,
    WEATHER_BAD_ANSWER,
    call_tool,
    condition_from_code,
    get_weather,
)

_DATES = [
    "2026-10-29",
    "2026-10-30",
    "2026-10-31",
    "2026-11-01",
    "2026-11-02",
    "2026-11-03",
    "2026-11-04",
]
_HIGHS = [22, 21, 20, 19, 18, 17, 16]
_LOWS = [14, 13, 12, 11, 10, 9, 8]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail if a test reaches httpx.get without supplying its own mock."""

    def refuse(*args, **kwargs):
        raise RuntimeError("tests must not use the network")

    monkeypatch.setattr("weather.httpx.get", refuse)


def _install_answers(monkeypatch, answers):
    pending = list(answers)

    def fake_get_json(url, params):
        if not pending:
            raise AssertionError(f"unexpected _get_json call for {url}")
        return pending.pop(0)

    monkeypatch.setattr("weather._get_json", fake_get_json)


def _geocode(name, latitude=35.7, longitude=139.7):
    return {"results": [{"name": name, "latitude": latitude, "longitude": longitude}]}


def _forecast(temperature, weather_code, daily_codes):
    return {
        "current": {"temperature_2m": temperature, "weather_code": weather_code},
        "daily": {
            "time": list(_DATES),
            "temperature_2m_max": list(_HIGHS),
            "temperature_2m_min": list(_LOWS),
            "weather_code": list(daily_codes),
        },
    }


def _expected_forecast(daily_codes):
    return [
        {
            "date": date,
            "high_c": high,
            "low_c": low,
            "condition": condition_from_code(code),
        }
        for date, high, low, code in zip(_DATES, _HIGHS, _LOWS, daily_codes)
    ]


def test_get_weather_tokyo(monkeypatch):
    daily_codes = [0, 1, 3, 45, 71, 80, 95]
    _install_answers(
        monkeypatch,
        [
            _geocode("Tokyo"),
            _forecast(18, 0, daily_codes),
        ],
    )

    report = json.loads(get_weather("Tokyo"))

    assert report["city"] == "Tokyo"
    assert report["temperature_c"] == 18
    assert report["condition"] == "Clear"
    assert report["forecast"] == _expected_forecast(daily_codes)
    assert len(report["forecast"]) == 7


def test_get_weather_unknown_city(monkeypatch):
    daily_codes = [4, 4, 4, 4, 4, 4, 4]
    _install_answers(
        monkeypatch,
        [
            _geocode("Paris", latitude=48.8, longitude=2.3),
            _forecast(20, 4, daily_codes),
        ],
    )

    report = json.loads(get_weather("Paris"))

    assert report["city"] == "Paris"
    assert report["temperature_c"] == 20
    assert report["condition"] == "Unknown"
    assert report["forecast"] == _expected_forecast(daily_codes)
    assert len(report["forecast"]) == 7


@pytest.mark.parametrize(
    ("code", "condition"),
    [
        (0, "Clear"),
        (61, "Rain"),
        (95, "Thunderstorm"),
        (123, "Unknown"),
    ],
)
def test_condition_from_code(code, condition):
    assert condition_from_code(code) == condition


def test_city_not_found(monkeypatch):
    _install_answers(monkeypatch, [{"results": []}])

    with pytest.raises(CITY_NOT_FOUND) as raised:
        get_weather("Atlantis")

    message = str(raised.value)
    assert "Atlantis" in message
    assert "Check the spelling" in message


def test_weather_bad_answer_when_forecast_missing_fields(monkeypatch):
    _install_answers(
        monkeypatch,
        [
            _geocode("Tokyo"),
            {"current": {"temperature_2m": 18}},
        ],
    )

    with pytest.raises(WEATHER_BAD_ANSWER) as raised:
        get_weather("Tokyo")

    message = str(raised.value)
    assert "does not understand" in message
    assert "Try again" in message


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
