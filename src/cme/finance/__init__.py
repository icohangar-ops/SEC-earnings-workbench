"""Finance domain adapters used by CHP/CFO OS sessions."""

from cme.finance.capital_allocation import (
    CapitalAllocationInput,
    build_capital_allocation_case,
)

__all__ = [
    "CapitalAllocationInput",
    "build_capital_allocation_case",
]
