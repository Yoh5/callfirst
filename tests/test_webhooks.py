"""Threat (c): forged or replayed webhooks."""
from __future__ import annotations

from datetime import timedelta

import pytest

from callfirst import webhooks
from callfirst.webhooks import Rejected

from .conftest import DOORBELL, KEY, T0, payload


def read(raw, header=None, now=T0):
    return webhooks.read(KEY, raw, header if header is not None else webhooks.sign(KEY, raw), now)


def test_genuine_webhook_is_read():
    e = read(payload("motion_detected", DOORBELL, T0, "human", request_id="r1"))
    assert (e.kind, e.device_id, e.at, e.request_id, e.is_person) == \
        ("motion_detected", DOORBELL, T0, "r1", True)


def test_signature_format_is_rings():
    raw = b'{"a":1}'
    # The value ring-sandbox's own signer produces for the same key and body.
    assert webhooks.sign("k", raw) == \
        "sha256=c3a92ff9e274cdcce27a58c15a78ec6dcbbdbd0038a87e7a11baef2028fd8bff"


@pytest.mark.parametrize("header", ["", "sha256=", "sha256=00", "sha256=" + "0" * 64,
                                    "md5=abc", "sha256=é"])
def test_bad_signatures_are_rejected(header):
    raw = payload("button_press", DOORBELL, T0)
    with pytest.raises(Rejected, match="bad signature"):
        webhooks.read(KEY, raw, header, T0)


def test_a_body_changed_after_signing_is_rejected():
    raw = payload("button_press", DOORBELL, T0)
    signature = webhooks.sign(KEY, raw)
    with pytest.raises(Rejected, match="bad signature"):
        read(raw.replace(DOORBELL.encode(), b"db-2"), signature)


def test_signed_with_another_key_is_rejected():
    raw = payload("button_press", DOORBELL, T0)
    with pytest.raises(Rejected, match="bad signature"):
        read(raw, webhooks.sign("someone-else", raw))


def test_no_key_configured_rejects_everything():
    raw = payload("button_press", DOORBELL, T0)
    with pytest.raises(Rejected):
        webhooks.read("", raw, webhooks.sign("", raw), T0)


def test_a_capture_replayed_later_is_stale():
    raw = payload("button_press", DOORBELL, T0)
    with pytest.raises(Rejected, match="stale"):
        read(raw, now=T0 + webhooks.MAX_AGE + timedelta(seconds=1))


def test_a_late_but_fresh_delivery_is_accepted():
    raw = payload("button_press", DOORBELL, T0)
    assert read(raw, now=T0 + webhooks.MAX_AGE - timedelta(seconds=1))


def test_a_delivery_dated_in_the_future_is_rejected():
    raw = payload("button_press", DOORBELL, T0, sent=T0 + timedelta(minutes=5))
    with pytest.raises(Rejected, match="future"):
        read(raw)


def test_signed_garbage_is_malformed_not_a_crash():
    for raw in (b"not json", b"{}", b'{"meta":{},"data":{}}', b"[]"):
        with pytest.raises(Rejected, match="malformed"):
            read(raw)


def test_event_kinds_we_do_not_use_are_ignored():
    assert read(payload("flood_detected", DOORBELL, T0)) is None
