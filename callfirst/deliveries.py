"""Declared deliveries: read by anything, validated by code.

The resident pastes a carrier's notification. A reader proposes fields -
``read`` below with rules, or a language model for messy text - and the
resident confirms them. Whatever proposed them, ``validate`` decides.

This is the defence against threat (b) in DESIGN.md: a scammer's text crafted
to make the courier look expected. The reader may be fooled; it has no power.
``validate`` looks at the pasted text itself, not at what the reader said
about it:

- a collection is refused, by words found in the text, whatever the reader
  labelled it;
- the tracking number must match the carrier's format *and* appear in the
  pasted text, so it cannot be invented;
- the window must be soon and short.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from .household import Delivery, iso

TRACKING = {
    "UPS": re.compile(r"1Z[0-9A-Z]{16}"),
    "USPS": re.compile(r"9[1-5]\d{20}"),
    "FedEx": re.compile(r"\d{12}|\d{15}"),
    "DHL": re.compile(r"\d{10}"),
    "Amazon": re.compile(r"TBA\d{12}"),
}
CARRIER_NAMES = {
    "UPS": ("ups",),
    "USPS": ("usps", "postal service"),
    "FedEx": ("fedex",),
    "DHL": ("dhl",),
    "Amazon": ("amazon",),
}
# Nobody legitimate sends someone to take cash, gold or cards from a home.
COLLECTION = re.compile(
    r"\b(collect\w*|pick(?:ing)?[\s-]?up|pickup|hand\s+(?:over|it|them|the)|"
    r"cash|gold|bullion|silver\s+bars?|withdraw\w*|gift\s+cards?|bank\s+cards?|"
    r"debit\s+cards?|credit\s+cards?|pin\s+(?:code|number)|safe\s+keeping|"
    r"safekeeping|secure\s+(?:your|the)\s+(?:funds|money|assets))\b",
    re.IGNORECASE,
)
HORIZON = timedelta(days=14)
LONGEST = timedelta(hours=12)


@dataclass(frozen=True)
class Proposal:
    """What a reader thinks the notification says. Untrusted by construction."""
    carrier: str | None = None
    tracking: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    signature_required: bool = False


@dataclass(frozen=True)
class Verdict:
    delivery: Delivery | None
    refusals: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.delivery is not None


def _compact(text: str) -> str:
    return re.sub(r"[\s-]", "", text).upper()


def read(text: str) -> Proposal:
    """Rule-based reader: carrier and tracking number. The window is left to the
    resident, who knows it better than a regex does."""
    lowered = text.lower()
    carrier = next((c for c, names in CARRIER_NAMES.items()
                    if any(re.search(rf"\b{re.escape(n)}\b", lowered) for n in names)), None)
    tracking = None
    compact = _compact(text)
    for name in ([carrier] if carrier else []) + [c for c in TRACKING if c != carrier]:
        found = TRACKING[name].search(compact)
        if found:
            carrier, tracking = carrier or name, found.group(0)
            break
    signature = bool(re.search(r"signature (?:is )?required|requires? (?:a )?signature",
                               lowered))
    return Proposal(carrier, tracking, signature_required=signature)


def validate(text: str, proposal: Proposal, now: datetime) -> Verdict:
    refusals = []
    words = sorted({m.group(0).lower() for m in COLLECTION.finditer(text)})
    if words:
        refusals.append("this reads as a collection, not a delivery ("
                        + ", ".join(words) + "); nobody legitimate collects from a home")
    if proposal.carrier not in TRACKING:
        refusals.append("unknown carrier")
    elif not proposal.tracking or not TRACKING[proposal.carrier].fullmatch(
            _compact(proposal.tracking)):
        refusals.append(f"not a {proposal.carrier} tracking number")
    elif _compact(proposal.tracking) not in _compact(text):
        refusals.append("the tracking number is not in the pasted text")
    if not proposal.start or not proposal.end:
        refusals.append("no delivery window")
    elif proposal.end <= proposal.start:
        refusals.append("the window ends before it starts")
    elif proposal.end - proposal.start > LONGEST:
        refusals.append("the window is longer than 12 hours")
    elif proposal.end < now or proposal.start > now + HORIZON:
        refusals.append("the window is not within the next 14 days")
    if refusals:
        return Verdict(None, tuple(refusals))
    return Verdict(Delivery(proposal.carrier, _compact(proposal.tracking),
                            iso(proposal.start), iso(proposal.end),
                            proposal.signature_required))
