"""Telling the trusted people: email.

Two mailers. ``FileMailer`` writes each message as an .eml file (the default,
and what the tests and the demo use); ``SmtpMailer`` sends it for real when
SMTP_HOST is set. SMS would cost money and add nothing to the argument.

The schedule never goes into an alert (threat (d) in DESIGN.md): an alert says
what happened at the door, not when the resident is usually alone.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

from .household import clock

SUBJECTS = {
    "answered": "Call First: the door was answered for an unexpected visitor",
    "heightened": "Call First: an unexpected visitor is at the door again",
    "blind": "Call First: the doorbell went offline during a visit",
    "change": "Call First: a change to the protection",
}
ACTION = {
    "answered": "Call {name} now. If money or valuables are being handed over, ask for the "
                "family word, and say plainly that it is a scam.",
    "heightened": "Call {name} now, before the door is opened.",
    "blind": "Call {name} now: nobody can see what is happening at the door.",
    "change": "If you did not expect this, call {name} and ask who suggested it.",
}
CONFIDENCE = {
    "strong": "The door sensor saw the door open.",
    "weak": "Inferred from how long the visitor stayed. The doorbell cannot see the door itself.",
}


def image_type(data: bytes) -> str:
    """The Partner API is asked for JPEG; the emulator's placeholder is PNG."""
    return "png" if data[1:4] == b"PNG" else "jpeg"


def compose(alert: dict, resident: str, timezone: str, sender: str, base_url: str,
            image: bytes | None = None, report_id: int | None = None,
            report_key: str | None = None) -> EmailMessage:
    at = datetime.fromisoformat(alert["at"]).astimezone(ZoneInfo(timezone))
    reason = alert["reason"]
    lines = [
        f"{resident}'s front door, {at:%A, %B} {at.day}, {clock(at)}.",
        "",
        alert["detail"],
    ]
    if alert.get("confidence"):
        lines += ["", CONFIDENCE[alert["confidence"]]]
    lines += ["", ACTION[reason].format(name=resident)]
    if report_id is not None:
        # The key, when there is one, so the link opens on the phone the alert
        # arrived on rather than only in the browser that opened the invitation.
        lien = f"{base_url}/family/report/{report_id}"
        if report_key:
            lien += f"?k={report_key}"
        lines += ["", f"Report sheet, ready for the FBI (ic3.gov) and the FTC: {lien}"]
    lines += ["", f"-- Call First. You receive this because {resident} named you as a trusted "
                  "person. You can stop at any time from your page."]

    message = EmailMessage()
    message["Subject"] = SUBJECTS[reason]
    message["From"] = sender
    message["To"] = ", ".join(alert["recipients"])
    message.set_content("\n".join(lines))
    if image:
        kind = image_type(image)
        message.add_attachment(image, maintype="image", subtype=kind,
                               filename=f"front-door-{at:%Y%m%d-%H%M}.{'jpg' if kind == 'jpeg' else kind}")
    return message


class FileMailer:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)

    def send(self, message: EmailMessage) -> bool:
        n = len(list(self.folder.glob("*.eml")))
        (self.folder / f"{n + 1:04d}.eml").write_bytes(bytes(message))
        return True


class SmtpMailer:
    def __init__(self, host: str, port: int, user: str, password: str):
        self.host, self.port, self.user, self.password = host, port, user, password

    def send(self, message: EmailMessage) -> bool:
        try:
            with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                if self.user:
                    smtp.login(self.user, self.password)
                smtp.send_message(message)
            return True
        except (smtplib.SMTPException, OSError):
            return False


def from_env(data: Path):
    host = os.environ.get("SMTP_HOST")
    if not host:
        return FileMailer(data / "mail")
    return SmtpMailer(host, int(os.environ.get("SMTP_PORT", "587")),
                      os.environ.get("SMTP_USER", ""), os.environ.get("SMTP_PASSWORD", ""))


def invitation(person, resident: str, sender: str, link: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = f"{resident} named you as a trusted person in Call First"
    message["From"] = sender
    message["To"] = person.email
    message.set_content("\n".join([
        f"Hello {person.name},",
        "",
        f"{resident} uses Call First on their Ring doorbell against courier scams: when an "
        "unexpected visitor rings, a reminder plays indoors, and if the door is opened for "
        "them, you are told at once.",
        "",
        f"{resident} chose you. Your page shows whether the protection is on, and every "
        "alert. It does not show their schedule.",
        "",
        f"Your page: {link}",
        "",
        "This link is personal; do not forward it. You can stop receiving alerts from the "
        "page at any time.",
    ]))
    return message
