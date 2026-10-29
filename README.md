# function-calling

This folder is for learning **LLM function calling**: the model can ask to trigger code that I (the developer) write.

The model never runs anything itself. It replies with "please call this function with these inputs," my code runs the function, and I hand the result back so the model can finish its answer.

## Setup

```
python3 -m venv .venv
source .venv/bin/activate
```
