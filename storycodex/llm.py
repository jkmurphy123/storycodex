from __future__ import annotations

import os
import sys
from typing import Any
from urllib.parse import urlparse

import httpx

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_OPENAI_BASE = "https://api.openai.com/v1"
DEFAULT_TIMEOUT_SECONDS = 240
PROBE_TIMEOUT_SECONDS = 3.0


def get_base_url() -> str:
    return os.getenv("STORYCODEX_BASE_URL", DEFAULT_OPENAI_BASE)


def get_api_key() -> str | None:
    return os.getenv("OPENAI_API_KEY")


def get_default_model() -> str:
    return os.getenv("STORYCODEX_MODEL", DEFAULT_MODEL)


def get_backend_setting() -> str:
    return os.getenv("STORYCODEX_BACKEND", "auto").lower()


def get_timeout_seconds() -> float:
    raw = os.getenv("STORYCODEX_TIMEOUT_SECONDS")
    if raw is None:
        return float(DEFAULT_TIMEOUT_SECONDS)
    try:
        return float(int(raw))
    except ValueError as exc:
        raise ValueError("STORYCODEX_TIMEOUT_SECONDS must be an integer") from exc


def debug_enabled() -> bool:
    value = os.getenv("STORYCODEX_DEBUG_LLM", "")
    return value.lower() in {"1", "true", "yes", "on"}


def debug_log(message: str) -> None:
    print(message, file=sys.stderr)


def ensure_openai_base(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    parsed = urlparse(normalized)
    if "/v1" in parsed.path:
        return normalized
    return f"{normalized}/v1"


def resolve_backend(base_url: str, backend: str) -> tuple[str, str]:
    normalized = base_url.rstrip("/")
    backend = backend.lower()
    if backend not in {"openai", "ollama", "auto"}:
        raise ValueError("STORYCODEX_BACKEND must be one of: openai, ollama, auto")

    if backend == "openai":
        return "openai", ensure_openai_base(normalized)
    if backend == "ollama":
        return "ollama", normalized

    parsed = urlparse(normalized)
    if "/v1" in parsed.path:
        return "openai", ensure_openai_base(normalized)

    probe_url = f"{normalized}/v1/models"
    if probe_openai_models(probe_url):
        return "openai", ensure_openai_base(normalized)
    return "ollama", normalized


def probe_openai_models(url: str) -> bool:
    try:
        with httpx.Client(timeout=PROBE_TIMEOUT_SECONDS) as client:
            response = client.get(url)
        return response.status_code == 200
    except httpx.RequestError:
        return False


def chat(
    messages: list[dict[str, Any]],
    model: str,
    temperature: float = 0.4,
    max_tokens: int | None = None,
) -> str:
    base_url = get_base_url()
    backend, resolved_base = resolve_backend(base_url, get_backend_setting())

    api_key = get_api_key()
    if backend == "openai" and not api_key and resolved_base == DEFAULT_OPENAI_BASE:
        raise RuntimeError("OPENAI_API_KEY is required when using the OpenAI API")

    headers = {"Content-Type": "application/json"}
    if backend == "openai" and api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    if backend == "openai":
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        url = f"{resolved_base}/chat/completions"
    else:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        url = f"{resolved_base}/api/chat"

    if debug_enabled():
        debug_log(f"[storycodex.llm] backend={backend} url={url}")
        debug_log(f"[storycodex.llm] request={payload}")

    try:
        with httpx.Client(timeout=get_timeout_seconds()) as client:
            response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"LLM request failed (backend={backend}, url={url}): {exc}"
        ) from exc
    if debug_enabled():
        debug_log(f"[storycodex.llm] status={response.status_code}")
        debug_log(f"[storycodex.llm] response={response.text}")

    data = response.json()
    try:
        if backend == "openai":
            return data["choices"][0]["message"]["content"]
        return data["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            f"Unexpected response format (backend={backend}, url={url})"
        ) from exc
