# AI Governance Controls

This workbench now adds proof-carrying claim gates to the research audit trail.
Each claim-level audit entry receives a certificate with:

- claim hash
- producing agent
- pass/reject status
- reason
- allocated share of the global risk budget
- safe fallback for rejected claims

Rejected claims should be omitted, marked unknown, or routed for human review
before final publication.

Attribution:

- Proof-carrying gate and global risk-budget pattern adapted from Georgios
  Fradelos, PhD, *Certifiable AI Safety Theory (CAST): Convex-Analytic,
  Measure-Theoretic, and Proof-Carrying Deployment Gates for Tool-Using LLM
  Systems*, Geneva, February 12, 2026. Local source:
  `AI Governance papers/ssrn-6307158.pdf`.
- Progressive-output and observable-alignment ideas adapted from Georgios
  Fradelos, PhD, *A Mathematical Solution to the AI Alignment Problem:
  Topological Constraints on Action Distributions with Progressive
  Verification*, Geneva, January 14, 2026. Local source:
  `AI Governance papers/ssrn-6307060.pdf`.
