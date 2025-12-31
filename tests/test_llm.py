import httpx
import pytest

from storycodex import llm


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, timeout=None, get_response=None, post_response=None):
        self.timeout = timeout
        self.get_response = get_response
        self.post_response = post_response
        self.requests = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None):
        self.requests.append(("GET", url, None, headers))
        return self.get_response

    def post(self, url, json=None, headers=None):
        self.requests.append(("POST", url, json, headers))
        return self.post_response


def test_resolve_backend_prefers_openai_when_v1_in_url(monkeypatch):
    def fake_client(timeout=None):
        raise AssertionError("Probe should not be called")

    monkeypatch.setattr(httpx, "Client", fake_client)
    backend, base = llm.resolve_backend("http://localhost:8000/v1", "auto")
    assert backend == "openai"
    assert base == "http://localhost:8000/v1"


def test_resolve_backend_probe_success(monkeypatch):
    client_holder = {}

    def fake_client(timeout=None):
        client = FakeClient(get_response=FakeResponse(200, {}))
        client_holder["client"] = client
        return client

    monkeypatch.setattr(httpx, "Client", fake_client)
    backend, base = llm.resolve_backend("http://localhost:8000", "auto")

    assert backend == "openai"
    assert base == "http://localhost:8000/v1"
    assert client_holder["client"].requests[0][1] == "http://localhost:8000/v1/models"


def test_resolve_backend_probe_fail(monkeypatch):
    client_holder = {}

    def fake_client(timeout=None):
        client = FakeClient(get_response=FakeResponse(404, {}))
        client_holder["client"] = client
        return client

    monkeypatch.setattr(httpx, "Client", fake_client)
    backend, base = llm.resolve_backend("http://localhost:11434", "auto")

    assert backend == "ollama"
    assert base == "http://localhost:11434"
    assert client_holder["client"].requests[0][1] == "http://localhost:11434/v1/models"


def test_chat_openai_parsing(monkeypatch):
    client_holder = {}

    def fake_client(timeout=None):
        client = FakeClient(
            post_response=FakeResponse(
                200, {"choices": [{"message": {"content": "ok"}}]}
            )
        )
        client_holder["client"] = client
        return client

    monkeypatch.setattr(httpx, "Client", fake_client)
    monkeypatch.setenv("STORYCODEX_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("STORYCODEX_BACKEND", "openai")

    result = llm.chat([{"role": "user", "content": "hi"}], "model")

    assert result == "ok"
    assert client_holder["client"].requests[0][1] == "http://localhost:8000/v1/chat/completions"


def test_chat_ollama_parsing(monkeypatch):
    client_holder = {}

    def fake_client(timeout=None):
        client = FakeClient(post_response=FakeResponse(200, {"message": {"content": "ok"}}))
        client_holder["client"] = client
        return client

    monkeypatch.setattr(httpx, "Client", fake_client)
    monkeypatch.setenv("STORYCODEX_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("STORYCODEX_BACKEND", "ollama")

    result = llm.chat([{"role": "user", "content": "hi"}], "model")

    assert result == "ok"
    assert client_holder["client"].requests[0][1] == "http://localhost:11434/api/chat"
