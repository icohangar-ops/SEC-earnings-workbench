"""Devil's advocate helpers for CHP sessions."""
from __future__ import annotations


def merge_structural_vulnerabilities(existing: list[str], new_items: list[str]) -> list[str]:
    merged = list(existing)
    for item in new_items:
        if item not in merged:
            merged.append(item)
    return merged
