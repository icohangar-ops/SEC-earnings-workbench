"""Helpers for building and validating CHP dossiers."""
from __future__ import annotations

from cme.chp.models import Dossier


def validate_dossier(dossier: Dossier) -> list[str]:
    return dossier.validate()
