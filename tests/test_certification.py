from dataclasses import dataclass

from cme.chp.certification import build_proof_certificates, certify_claim


@dataclass
class Claim:
    agent: str
    claim: str
    grounding_source: str
    grounding_confidence: str
    risk_flag: str = ""


def test_certify_claim_passes_verified_medium_claim() -> None:
    cert = certify_claim(
        Claim("Fundamentals", "Revenue rose from the 10-K.", "SEC EDGAR", "medium"),
        allocated_risk_budget=0.01,
    )

    assert cert.status == "PASS"
    assert cert.claim_hash


def test_certify_claim_rejects_inferred_claim() -> None:
    cert = certify_claim(
        Claim("Markets", "Multiple expansion is likely.", "inferred", "high"),
        allocated_risk_budget=0.01,
    )

    assert cert.status == "REJECT"
    assert cert.fallback == "mark_unknown_or_remove_claim"


def test_build_proof_certificates_allocates_global_budget() -> None:
    certs = build_proof_certificates(
        [
            Claim("A", "one", "SEC EDGAR", "high"),
            Claim("B", "two", "FRED", "medium"),
        ],
        global_risk_budget=0.02,
    )

    assert [cert.allocated_risk_budget for cert in certs] == [0.01, 0.01]
