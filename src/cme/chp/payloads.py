"""Payload-integrity helpers for CHP packet exchange."""
from __future__ import annotations

import random
import string
from dataclasses import dataclass


@dataclass(frozen=True)
class PayloadEnvelope:
    route: str
    payload_id: str
    body: str

    def render(self) -> str:
        return (
            f"BEGIN_PAYLOAD [{self.route}] [{self.payload_id}]\n"
            f"{self.body}\n"
            f"END_PAYLOAD [{self.route}] [{self.payload_id}]"
        )


def _make_payload_id() -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choice(chars) for _ in range(6))


def build_payload_envelope(body: str, *, route: str = "RX", payload_id: str | None = None) -> PayloadEnvelope:
    return PayloadEnvelope(route=route, payload_id=payload_id or _make_payload_id(), body=body)


def validate_payload_envelope(rendered: str) -> bool:
    lines = [line.rstrip() for line in rendered.strip().splitlines()]
    if len(lines) < 3:
        return False
    first, last = lines[0], lines[-1]
    if not first.startswith("BEGIN_PAYLOAD [") or not last.startswith("END_PAYLOAD ["):
        return False
    return first.replace("BEGIN_PAYLOAD", "", 1).strip() == last.replace("END_PAYLOAD", "", 1).strip()


def payload_echo_confirmed(route: str, payload_id: str, echo: str) -> bool:
    return echo.strip() == f"[{route}] [{payload_id}] CONFIRMED"


def extract_payload_id(rendered: str) -> str | None:
    lines = [line.rstrip() for line in rendered.strip().splitlines()]
    if not lines:
        return None
    first = lines[0]
    if not first.startswith("BEGIN_PAYLOAD ["):
        return None
    parts = first.split("[")
    if len(parts) < 3:
        return None
    payload_id = parts[2].rstrip("]")
    return payload_id.strip()
