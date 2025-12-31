from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_MODEL = "gpt-4o-mini"


def get_base_url() -> str:
    return os.getenv("STORYCODEX_BASE_URL", "https://api.openai.com/v1")


def get_api_key() -> str | None:
    return os.getenv("OPENAI_API_KEY")


def get_default_model() -> str:
    return os.getenv("STORYCODEX_MODEL", DEFAULT_MODEL)


def chat_completion(messages: list[dict[str, Any]], model: str) -> str:
    base_url = get_base_url().rstrip("/")
    api_key = get_api_key()
    if not api_key and base_url == "https://api.openai.com/v1":
        raise RuntimeError("OPENAI_API_KEY is required when using the OpenAI API")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {"model": model, "messages": messages}
    url = f"{base_url}/chat/completions"

    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, json=payload, headers=headers)
    response.raise_for_status()
    data = response.json()

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Unexpected response format from LLM") from exc
