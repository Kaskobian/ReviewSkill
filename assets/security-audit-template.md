# Security Audit Report Template

Copy for OWASP audits. Keep it to what was verified: no filler, no repeated findings.
Procedure: [OWASP Security Audit](../reference/owasp-security-audit.md). Fixing: [Remediation Playbook](../reference/remediation-playbook.md).

---

## Scope

- **Target:** [repo / service / directory / PR] at [commit or branch]
- **Level:** ASVS L1 / L2 / L3
- **Assets:** [credentials, PII, payments, admin functions, ...]
- **Entry points:** [HTTP routes, queues, webhooks, CLI, LLM tools]
- **Trust boundaries:** [browser → API, API → DB, third-party → us, user text → LLM → tools]
- **Not in scope:** [infrastructure, mobile client, ...]

## Checks run

| Check | Command | Result |
|-------|---------|--------|
| Security scan | `python scripts/security-scan.py <path>` | [N candidates: X high / Y medium / Z low] |
| Dependency audit | `python scripts/dep-audit.py <path>` | [N packages, X advisories, Y in CISA KEV; or "not run: reason"] |
| Tests | [command] | [real result, or "not run: reason"] |

> Report a check as passing only after seeing it pass.

## Findings

🔴 **[blocking]** [Title] — `path/file.ext:line`
OWASP: [A0X:2025 Name] · CWE-[n] · Confidence: confirmed / unverified
Source → sink: [entry point] → [path] → [dangerous operation], [guard: none / bypassable because ...]
Why: [what an attacker gains, in one line]
Fix: [canonical fix + regression test to add]

🟡 **[important]** [Title] — `path/file.ext:line`
OWASP: [...] · CWE-[n] · Confidence: [...]
Why: [...]
Fix: [...]

> Same issue in more places? One finding + "also at: file:line, file:line, ... (N total)".

## OWASP coverage

| Category | Status |
|----------|--------|
| A01 Broken Access Control | checked: N findings / checked: none / not checked (reason) |
| A02 Security Misconfiguration | |
| A03 Software Supply Chain Failures | |
| A04 Cryptographic Failures | |
| A05 Injection | |
| A06 Insecure Design | |
| A07 Authentication Failures | |
| A08 Software or Data Integrity Failures | |
| A09 Security Logging and Alerting Failures | |
| A10 Mishandling of Exceptional Conditions | |
| API Top 10 (if an API) | |
| LLM Top 10 (if AI features) | |

## Top risks (fix in this order)

1. [#, title]: [rough size: hours / days / weeks]
2. ...
3. ...

## Remediation work list

| # | Finding | Location | Severity | Status |
|---|---------|----------|----------|--------|
| 1 | | | 🔴 | todo |

## Not verified / out of scope

- [what couldn't be traced, which files weren't read, what needs runtime testing]
