"""Round progression helpers for CHP sessions."""
from __future__ import annotations

from cme.chp.models import Phase


def next_round(phase: Phase, round_number: int) -> tuple[Phase, int]:
    if phase == Phase.FOUNDATION:
        return Phase.SPEC, 1
    if phase == Phase.SPEC and round_number >= 2:
        return Phase.IMPLEMENTATION, 3
    return phase, round_number + 1
