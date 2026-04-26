"""Command-line entry point for the SEC / Earnings / Company Research Workbench."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from cme.bridge import EntryPoint
from cme.chp import (
    CHPOrchestrator,
    DecisionRegistry,
    Phase,
    ThirdPartyValidation,
    ValidationResult,
)
from cme.context import ContextEngine, Entity, Task
from cme.orchestrator import EnterpriseOrchestrator
from cme.research import (
    CompanyBrief,
    InitiationBrief,
    ResearchTaskType,
    ResearchWorkbench,
    SECDeepDiveBrief,
)
from cme.research.data import AlphaVantageClient, EdgarClient, EdgarError, FredClient


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Tiny .env loader (no external dep). Skips lines that are blank/comments."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def _registry_path(args: argparse.Namespace) -> Path:
    return Path(getattr(args, "registry", ".chp_registry.json"))


def _default_agents() -> List:
    from demo import DiligenceAgent, FundamentalsAgent, MarketsAgent  # noqa: WPS433

    return [FundamentalsAgent(), DiligenceAgent(), MarketsAgent()]


def _build_workbench(args: argparse.Namespace) -> ResearchWorkbench:
    registry = DecisionRegistry()
    if args.registry:
        registry = DecisionRegistry()  # registry persistence handled by save flow if needed
    return ResearchWorkbench(
        agents=_default_agents(),
        registry=registry,
    )


def _emit(report, args: argparse.Namespace) -> int:
    text = report.render()
    if args.out_md:
        Path(args.out_md).write_text(text)
        print(f"Wrote markdown report to {args.out_md}")
    if args.json:
        out = {
            "task": report.brief.task_type.value,
            "decision_id": report.case.decision_id,
            "lock_state": report.case.status.value,
            "foundation_score": report.case.foundation_score,
            "r0_verdict": report.r0_verdict.value,
            "foundation_verdict": report.foundation_verdict.value,
            "data_warnings": report.data_warnings,
            "agents": [
                {
                    "name": t.agent,
                    "recommendation": t.trace.recommendation,
                    "confidence": t.trace.confidence.value,
                    "playbook_deltas": t.deltas_applied,
                }
                for t in report.turns
            ],
            "edgar_filings": [f.as_dict() for f in report.edgar_filings],
            "artifact_title": report.artifact.title,
            "sections": [
                {"heading": s["heading"], "bullets": s.get("bullets", [])}
                for s in report.artifact.sections
            ],
        }
        print(json.dumps(out, indent=2))
    else:
        print(text)
    return 0


# --- Subcommands ------------------------------------------------------------


def _cmd_company_research(args: argparse.Namespace) -> int:
    bench = _build_workbench(args)
    brief = CompanyBrief(
        title=args.title,
        company=args.company,
        ticker=args.ticker,
        problem=args.problem,
        industry=args.industry or "",
        peers=args.peer or [],
        revenue_streams_hint=args.revenue_stream or [],
        customer_segments_hint=args.segment or [],
        geography_hint=args.geo or [],
        constraints=args.constraint or [],
    )
    return _emit(bench.run(brief), args)


def _cmd_sec_deep_dive(args: argparse.Namespace) -> int:
    bench = _build_workbench(args)
    brief = SECDeepDiveBrief(
        title=args.title,
        company=args.company,
        ticker=args.ticker,
        problem=args.problem,
        industry=args.industry or "",
        peers=args.peer or [],
        filings_in_scope=args.filings or ["10-K", "10-Q", "8-K", "DEF 14A"],
        red_flag_focus=args.red_flag or [],
        fiscal_years_back=args.years_back,
        constraints=args.constraint or [],
    )
    return _emit(bench.run(brief), args)


def _cmd_initiation(args: argparse.Namespace) -> int:
    bench = _build_workbench(args)
    brief = InitiationBrief(
        title=args.title,
        company=args.company,
        ticker=args.ticker,
        problem=args.problem,
        industry=args.industry or "",
        peers=args.peer or [],
        rating_seed=args.rating,
        target_price_usd=args.target,
        valuation_method_preference=args.method,
        forecast_years=args.years,
        key_drivers_hint=args.driver or [],
        investment_thesis_seed=args.thesis or "",
        constraints=args.constraint or [],
    )
    return _emit(bench.run(brief), args)


def _cmd_data(args: argparse.Namespace) -> int:
    """Pull AV OVERVIEW + FRED macro panel + EDGAR filings for a single ticker."""
    av = AlphaVantageClient()
    fred = FredClient()
    edgar = EdgarClient()
    out = {
        "alphavantage_live": av.is_live,
        "fred_live": fred.is_live,
        "edgar_live": edgar.is_live,  # always True; included for symmetry
    }
    if av.is_live and args.ticker:
        ov = av.overview(args.ticker)
        if ov:
            out["overview"] = {
                "Symbol": ov.get("Symbol"),
                "Name": ov.get("Name"),
                "Sector": ov.get("Sector"),
                "Industry": ov.get("Industry"),
                "MarketCapitalization": ov.get("MarketCapitalization"),
                "PERatio": ov.get("PERatio"),
                "ProfitMargin": ov.get("ProfitMargin"),
                "LatestQuarter": ov.get("LatestQuarter"),
            }
    if fred.is_live:
        out["macro_panel"] = fred.macro_panel()
    if args.ticker:
        try:
            cik = edgar.cik_for(args.ticker)
            if cik is None:
                out["edgar"] = {"warning": f"no CIK match for ticker {args.ticker}"}
            else:
                recent = edgar.recent_filings(
                    args.ticker,
                    forms=["10-K", "10-Q", "8-K", "DEF 14A"],
                    limit=8,
                )
                eight_k_sweep = edgar.eight_ks_since_last_periodic(args.ticker)
                out["edgar"] = {
                    "cik": cik,
                    "company_name": edgar.company_name_for(args.ticker),
                    "recent_filings": [f.as_dict() for f in recent],
                    "eight_k_sweep_count": len(eight_k_sweep),
                    "eight_k_sweep": [f.as_dict() for f in eight_k_sweep[:5]],
                }
        except EdgarError as exc:
            out["edgar"] = {"error": str(exc)}
        except Exception as exc:
            out["edgar"] = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(out, indent=2))
    return 0


def _cmd_chp_start(args: argparse.Namespace) -> int:
    """Start a raw CHP capital-allocation session (legacy CHP demo)."""
    from cme.finance import CapitalAllocationInput, build_capital_allocation_case  # noqa: WPS433

    case, disclosure, attack = build_capital_allocation_case(
        CapitalAllocationInput(
            title=args.title,
            company=args.company,
            proposal_summary=args.problem,
            investment_amount_usd=args.amount,
            expected_payback_months=args.payback_months,
            minimum_runway_months=args.min_runway,
            current_runway_months=args.current_runway,
        )
    )
    registry = DecisionRegistry.load(_registry_path(args))
    orch = CHPOrchestrator(registry=registry)
    report = orch.run_initial_session(case=case, foundation_disclosure=disclosure, foundation_attack=attack)
    registry.save(_registry_path(args))
    print(f"decision_id: {case.decision_id}")
    print(f"foundation_verdict: {report.foundation_verdict.value}")
    print(f"r0_verdict: {report.r0_verdict.value}")
    print(f"status: {case.status.value}")
    return 0


def _cmd_chp_validate(args: argparse.Namespace) -> int:
    registry = DecisionRegistry.load(_registry_path(args))
    case = registry.get(args.decision_id)
    if not case:
        print(f"Unknown decision_id: {args.decision_id}", file=sys.stderr)
        return 1
    from cme.chp import apply_third_party_validation  # noqa: WPS433

    validation = ThirdPartyValidation(
        validator=args.validator,
        item=args.item,
        challenge=args.challenge,
        result=ValidationResult.CONFIRM if args.confirm else ValidationResult.REJECT,
        rationale=args.rationale,
    )
    apply_third_party_validation(case, validation)
    registry.save(_registry_path(args))
    print(f"status now: {case.status.value}")
    return 0


# --- Argument parser --------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="research-bench", description="SEC / Earnings / Company Research Workbench")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--title", required=True)
    common.add_argument("--company", required=True)
    common.add_argument("--ticker", required=True)
    common.add_argument("--problem", required=True)
    common.add_argument("--industry", default=None)
    common.add_argument("--peer", action="append", help="Repeatable peer ticker")
    common.add_argument("--constraint", action="append", help="Repeatable constraint")
    common.add_argument("--registry", default=".chp_registry.json")
    common.add_argument("--out-md", default=None, help="Also write the markdown report to this path")
    common.add_argument("--json", action="store_true", help="Emit a JSON summary alongside (or instead of) markdown")

    co = sub.add_parser("company-research", parents=[common])
    co.add_argument("--revenue-stream", action="append")
    co.add_argument("--segment", action="append")
    co.add_argument("--geo", action="append")
    co.set_defaults(func=_cmd_company_research)

    sec = sub.add_parser("sec-deep-dive", parents=[common])
    sec.add_argument("--filings", nargs="+", help="Filing types in scope (default: 10-K 10-Q 8-K DEF\\ 14A)")
    sec.add_argument("--red-flag", action="append")
    sec.add_argument("--years-back", type=int, default=3)
    sec.set_defaults(func=_cmd_sec_deep_dive)

    ini = sub.add_parser("initiation", parents=[common])
    ini.add_argument("--rating", default="Buy")
    ini.add_argument("--target", type=float, default=None)
    ini.add_argument("--method", default="EV/EBITDA")
    ini.add_argument("--years", type=int, default=3)
    ini.add_argument("--driver", action="append")
    ini.add_argument("--thesis", default=None)
    ini.set_defaults(func=_cmd_initiation)

    data = sub.add_parser("data", help="Inspect AlphaVantage + FRED key state and pull a snapshot")
    data.add_argument("--ticker", default=None, help="Pull AV OVERVIEW for this ticker")
    data.set_defaults(func=_cmd_data)

    chps = sub.add_parser("chp-start", help="Start a raw CHP capital-allocation session")
    chps.add_argument("--title", required=True)
    chps.add_argument("--company", required=True)
    chps.add_argument("--problem", required=True)
    chps.add_argument("--amount", type=float, default=2_500_000)
    chps.add_argument("--payback-months", type=int, default=14)
    chps.add_argument("--min-runway", type=int, default=12)
    chps.add_argument("--current-runway", type=int, default=18)
    chps.add_argument("--registry", default=".chp_registry.json")
    chps.set_defaults(func=_cmd_chp_start)

    chpv = sub.add_parser("chp-validate", help="Apply a third-party validation to advance to LOCKED")
    chpv.add_argument("--decision-id", required=True)
    chpv.add_argument("--validator", default="fresh_instance")
    chpv.add_argument("--item", default="Spec")
    chpv.add_argument("--challenge", default="Stress test before lock progression.")
    chpv.add_argument("--rationale", required=True)
    chpv.add_argument("--confirm", action="store_true", default=True)
    chpv.add_argument("--registry", default=".chp_registry.json")
    chpv.set_defaults(func=_cmd_chp_validate)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    _load_dotenv()
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
