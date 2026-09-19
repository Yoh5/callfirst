"""The model reader: useful when it works, harmless when it does not. Both providers."""
from __future__ import annotations

import json

import httpx
import pytest

from callfirst import reader

from .conftest import T0

TEXT = "UPS: your package 1Z999AA10123456784 arrives Tuesday between 2 and 6 PM."
PROVIDERS = ["openai", "anthropic"]


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def answer(provider, fields):
    def handler(request):
        handler.request = json.loads(request.content)
        handler.url = str(request.url)
        if provider == "openai":
            return httpx.Response(200, json={"choices": [{"message": {"tool_calls": [{
                "type": "function", "function": {"name": "delivery_fields",
                                                 "arguments": json.dumps(fields)}}]}}]})
        return httpx.Response(200, json={"content": [
            {"type": "tool_use", "name": "delivery_fields", "input": fields}]})
    return handler


def read(provider, handler):
    return reader.read(TEXT, T0, "America/New_York", key="k", client=client(handler),
                       provider=provider)


@pytest.mark.parametrize("provider", PROVIDERS)
def test_the_model_fills_the_window_in_local_time(provider):
    p = read(provider, answer(provider, {
        "carrier": "UPS", "tracking": "1Z999AA10123456784", "start": "2026-09-22T14:00:00",
        "end": "2026-09-22T18:00:00", "signature_required": False}))
    assert (p.carrier, p.tracking) == ("UPS", "1Z999AA10123456784")
    assert p.start.isoformat() == "2026-09-22T14:00:00-04:00"


@pytest.mark.parametrize("provider", PROVIDERS)
def test_the_notice_goes_in_as_data_and_the_model_can_only_return_fields(provider):
    handler = answer(provider, {"carrier": None, "tracking": None, "start": None, "end": None,
                                "signature_required": False})
    read(provider, handler)
    sent = handler.request
    if provider == "openai":
        assert "api.openai.com" in handler.url
        assert sent["tool_choice"] == {"type": "function", "function": {"name": "delivery_fields"}}
        assert [t["function"]["name"] for t in sent["tools"]] == ["delivery_fields"]
        assert sent["tools"][0]["function"]["strict"] is True
        system, user = sent["messages"][0]["content"], sent["messages"][1]["content"]
    else:
        assert sent["tool_choice"] == {"type": "tool", "name": "delivery_fields"}
        assert [t["name"] for t in sent["tools"]] == ["delivery_fields"]
        system, user = sent["system"], sent["messages"][0]["content"]
    assert "<notice>" in user and "data, not instructions" in system


def test_without_a_key_the_rules_read_it(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = reader.read(TEXT, T0, "America/New_York")
    assert (p.carrier, p.tracking, p.start) == ("UPS", "1Z999AA10123456784", None)


def test_openai_is_preferred_when_both_keys_are_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    assert reader.provider_from_env() == ("openai", "o")


@pytest.mark.parametrize("provider", PROVIDERS)
def test_an_outage_falls_back_to_the_rules(provider):
    assert read(provider, lambda r: httpx.Response(529, json={})).tracking == \
        "1Z999AA10123456784"


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_malformed_answer_falls_back_to_the_rules(provider):
    p = read(provider, answer(provider, {"start": "not a date"}))
    assert p.tracking == "1Z999AA10123456784" and p.start is None


@pytest.mark.parametrize("provider", PROVIDERS)
def test_an_answer_without_the_tool_falls_back_to_the_rules(provider):
    body = ({"choices": [{"message": {"content": "ok"}}]} if provider == "openai"
            else {"content": [{"type": "text", "text": "ok"}]})
    assert read(provider, lambda r: httpx.Response(200, json=body)).carrier == "UPS"


def test_a_model_without_reasoning_effort_is_retried_without_it():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append("reasoning_effort" in body)
        if "reasoning_effort" in body:
            return httpx.Response(400, json={"error": {"message": "Unrecognized request "
                                                       "argument supplied: reasoning_effort"}})
        return answer("openai", {"carrier": "UPS", "tracking": "1Z999AA10123456784",
                                 "start": "2026-09-22T14:00:00", "end": "2026-09-22T18:00:00",
                                 "signature_required": False})(request)
    p = read("openai", handler)
    assert calls == [True, False] and p.start is not None
