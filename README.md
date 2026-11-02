# function-calling

A small project for learning **LLM function calling**: the model asks your code to run a tool, your code runs it, and you hand the result back so the model can answer.

The model never runs anything itself. It's like a customer handing the kitchen an order slip: the model writes the slip, your code cooks.

## What it teaches

1. You describe a tool to the model (its name, what it does, what inputs it needs).
2. The model replies with a request like "please call `get_weather` with city = Reykjavik".
3. Your code runs the real function.
4. You send the result back, and the model turns it into a plain-English answer.

## Stack

- **Python 3**
- **OpenAI-compatible client**, pointed at xAI's Grok API (`https://api.x.ai/v1`)
- **Open-Meteo** for real weather data (free, no key needed)

## Set up

```
python3 -m venv .venv
source .venv/bin/activate
pip install openai pytest
export XAI_API_KEY="your-key-here"
```

Get a key at [console.x.ai](https://console.x.ai). Never commit your key. `.gitignore` already keeps `.env` files out.

## Run

```
python weather.py
```

## What the script does, step by step

1. Defines a `get_weather(city)` function that looks up the city with Open-Meteo, then fetches the current weather and a 7-day forecast.
2. Describes that function to the model as a tool, with a schema (`TOOLS`).
3. Sends a prompt asking for the forecast for the next several days.
4. Reads the model's tool call, checks the name and arguments, and runs `get_weather`.
5. Prints the forecast, then sends the result back so the model can write its final answer.

## Named failures

Errors have plain-English names so you can find the cause fast: `MISSING_KEY`, `BAD_REQUEST`, `RATE_LIMITED_OR_NO_CREDIT`, `UNREACHABLE`, `TOOL_NOT_FOUND`, `BAD_TOOL_ARGUMENTS`, `CITY_NOT_FOUND`, `WEATHER_UNREACHABLE` and `WEATHER_BAD_ANSWER`.

## License

Original project code and documentation are licensed under the [MIT License](LICENSE). This license does not relicense third-party incident reports, datasets, or other third-party material. Those materials remain subject to their original rights and terms; existing source links and attributions are retained.
