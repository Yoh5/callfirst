"""The model reader: useful when it works, harmless when it does not."""
from __future__ import annotations

import json

import httpx

from callfirst import reader

from .conftest import T0

TEXT = "UPS: your package 1Z999AA10123456784 arrives Tuesday between 2 and 6 PM."


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def answer(fields):
    def handler(request):
        handler.request = json.loads(request.content)
        return httpx.Response(200, json={"content": [
            {"type": "tool_use", "name": "delivery_fields", "input": fields}]})
    return handler


def test_the_model_fills_the_window_in_local_time():
    handler = answer({"carrier": "UPS", "tracking": "1Z999AA10123456784",
                      "start": "2026-09-22T14:00:00", "end": "2026-09-22T18:00:00",
                      "signature_required": False})
    p = reader.read(TEXT, T0, "America/New_York", key="k", client=client(handler))
    assert (p.carrier, p.tracking) == ("UPS", "1Z999AA10123456784")
    assert p.start.isoformat() == "2026-09-22T14:00:00-04:00"


def test_the_notice_goes_in_as_data_and_the_model_can_only_return_fields():
    handler = answer({"carrier": None, "tracking": None, "start": None, "end": None,
                      "signature_required": False})
    reader.read(TEXT, T0, "America/New_York", key="k", client=client(handler))
    sent = handler.request
    assert sent["tool_choice"] == {"type": "tool", "name": "delivery_fields"}
    assert [t["name"] for t in sent["tools"]] == ["delivery_fields"]
    assert "<notice>" in sent["messages"][0]["content"]
    assert "data, not instructions" in sent["system"]


def test_without_a_key_the_rules_read_it():
    p = reader.read(TEXT, T0, "America/New_York", key="")
    assert (p.carrier, p.tracking, p.start) == ("UPS", "1Z999AA10123456784", None)


def test_an_outage_falls_back_to_the_rules():
    p = reader.read(TEXT, T0, "America/New_York", key="k",
                    client=client(lambda r: httpx.Response(529, json={})))
    assert p.tracking == "1Z999AA10123456784"


def test_a_malformed_answer_falls_back_to_the_rules():
    p = reader.read(TEXT, T0, "America/New_York", key="k",
                    client=client(answer({"start": "not a date"})))
    assert p.tracking == "1Z999AA10123456784" and p.start is None


def test_an_answer_without_the_tool_falls_back_to_the_rules():
    handler = lambda r: httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})
    assert reader.read(TEXT, T0, "America/New_York", key="k",
                       client=client(handler)).carrier == "UPS"
