# Friction log — building on the Ring Partner API

Kept as we go, for Ring's developer experience team. Each entry: what we hit,
what it cost, what would have fixed it.

## No simulator

The hackathon rules point entrants to a simulator; none is published. The
official starter needs real devices and a Playground token that lasts 30
minutes. We built against [ring-sandbox](https://github.com/josepha-mayo/ring-sandbox),
a community emulator (MIT) written by another entrant, and at least two other
community emulators exist. *Fix:* an official emulator with a scripted-event
control plane, or a long-lived sandbox account with virtual devices.

## Chime audio: which sound, and set by whom?

The documentation says a chime's audio slots are visible and read-only, and
that playback picks a slot. It does not say how a partner puts its audio into a
slot, the format, or the length limit. The emulator names the slots
`ring-appstore-event-1/2`; we could not confirm that against the real API. It
decided a product question for us: per-family recorded messages are not
possible, so the reminder is a prepared recording. *Fix:* document slot
provisioning (console upload? per app or per install?) with formats and limits.

## Webhooks carry no timestamp header

The signature covers the body but there is no signed timestamp header, so
replay protection has to come from `meta.time` and `meta.request_id` inside the
body. That works, but the documentation does not say either field is
guaranteed, or how long Ring keeps retrying. *Fix:* state the retry window and
that `request_id` is unique per delivery (or per event, across retries).

## Webhooks arrive out of order

Nothing in the documentation promises ordering between devices. A door sensor
event can arrive before the doorbell press that preceded it; our rules handle it
(`tests/test_rules.py`), and the emulator's chaos mode (delivery jitter)
produces it on purpose. *Fix:* one sentence in the webhook docs.

## Contact sensors are Early Access

The one signal that makes "the door was opened" a fact rather than an inference
is behind the Early Access program. We designed a second mode for doorbell-only
homes and report its limits (a quick handover under 60 s is missed).
