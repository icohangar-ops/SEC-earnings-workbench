"""Model parity assessment for CHP sessions."""
from __future__ import annotations

from cme.chp.models import ModelParityCheck, ModelTier


def _infer_tier(model_name: str) -> ModelTier:
    name = model_name.lower()
    if any(token in name for token in ("opus", "max", "frontier")):
        return ModelTier.FRONTIER
    if any(token in name for token in ("gpt-5", "claude 4", "claude-4", "high")):
        return ModelTier.HIGH
    if any(token in name for token in ("sonnet", "4o", "mid", "gpt-4")):
        return ModelTier.MID
    if any(token in name for token in ("mini", "small", "haiku")):
        return ModelTier.SMALL
    return ModelTier.UNKNOWN


def assess_model_parity(origin_model: str, partner_model: str) -> ModelParityCheck:
    origin_tier = _infer_tier(origin_model)
    partner_tier = _infer_tier(partner_model)
    if origin_tier == ModelTier.UNKNOWN or partner_tier == ModelTier.UNKNOWN:
        delta = "MINOR"
        advisory = "One or both model tiers are unknown. Treat parity as advisory only."
    else:
        gap = abs(list(ModelTier).index(origin_tier) - list(ModelTier).index(partner_tier))
        if gap == 0:
            delta = "NONE"
            advisory = None
        elif gap == 1:
            delta = "MINOR"
            advisory = "Slight analytical weight difference. Monitor for dominance bias."
        else:
            delta = "SIGNIFICANT"
            advisory = None
    return ModelParityCheck(
        origin=origin_model,
        partner=partner_model,
        delta=delta,
        advisory=advisory,
    )
