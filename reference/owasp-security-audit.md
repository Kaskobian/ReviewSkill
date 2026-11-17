# OWASP Security Audit

A repeatable security audit mapped to **OWASP Top 10:2025**, the **OWASP API Security Top 10:2023**, and the **OWASP Top 10 for LLM Applications 2025**. Every finding carries an OWASP category and a CWE so it can be tracked, de-duplicated, and compared between audits.

Use it for: "security audit", "OWASP review", "pentest-style review of this code", "is this safe to ship", or the Security mode of a diff review. For a quick per-PR check the [Security Review Guide](security-review-guide.md) is enough; this guide is the full procedure.

To fix what an audit finds, follow the [Remediation Playbook](remediation-playbook.md). Never fix during the audit pass: mixing the two is where models lose track of both.

---

## Budget rules (read first)

An audit can eat a model's whole context window and still miss the bug. These rules keep it cheap and accurate on every model, from small to large:

1. **Scan before you read.** Run `scripts/security-scan.py` (repo) or `--diff` (change). Read only the files it points at, plus the code you need to trace each data flow. Don't read whole directories "for context".
2. **Load one section at a time.** Open the category section below that you're working on, not the whole guide plus every language guide.
3. **Trace, don't speculate.** A candidate becomes a finding only once you've followed the data from source to sink (§3). Five verified findings beat forty "possible" ones.
4. **Stop at the cap.** Report at most 10 findings per category at full detail; group the rest by pattern ("same issue in 14 more handlers: list"). Repeating one finding 14 times wastes tokens and buries the next category.
5. **Write each finding once.** No preamble, no restating the code back, no summary that repeats the findings table.

No tools at all (chat-only)? Ask the user for: the route/handler list, the auth middleware, the data-access layer, and dependency manifests. Audit those, and say what wasn't provided.

---

## 1. Scope and threat model (5 minutes, 10 lines of output)

Before looking for bugs, write down:

- **Assets**: what's worth stealing or breaking (credentials, PII, money movement, admin functions, model/system prompts).
- **Entry points**: HTTP routes, GraphQL resolvers, queues/consumers, webhooks, CLI args, file uploads, LLM tool calls.
- **Trust boundaries**: where data crosses from untrusted to trusted (browser → API, API → DB, third-party API → you, user text → LLM → tool).
- **Actors**: anonymous, authenticated user, tenant admin, staff/admin, other services.
- **Target level**: OWASP ASVS L1 (basic, any internet-facing app), L2 (most apps with sensitive data, the default), L3 (high value: payments, health, critical infrastructure).

If the map is wrong, everything downstream is wrong. State it so the user can correct it.

## 2. Automated triage

```bash
python scripts/security-scan.py path/to/repo          # whole codebase
git diff main...HEAD | python scripts/security-scan.py --diff   # only the change
python scripts/security-scan.py src --json --min-confidence medium
python scripts/security-scan.py --list-rules          # what it checks
```

Run `scripts/dep-audit.py <path>` for known-vulnerable dependency versions. It reads lock files and manifests (npm, pnpm, yarn, NuGet, PyPI, Go, Cargo, Composer, RubyGems, Gradle), checks the exact pinned versions against OSV.dev, marks CVEs in the CISA Known Exploited Vulnerabilities catalog, and `--nvd` fills missing CVSS scores from the NIST NVD. Report its real output, and treat a KEV entry as 🔴 when the vulnerable code path is reachable. If it can't run (no network), say so; never list CVEs from memory. The ecosystem tools are a cross-check when the environment allows: `npm audit`, `pip-audit`, `cargo audit`, `govulncheck ./...`, `bundle audit`, `composer audit`, `dotnet list package --vulnerable`, `mvn org.owasp:dependency-check-maven:check`. Report the real output. If they weren't run, say "dependency audit: not run (reason)".

The scanner produces **candidates**, never findings. It's pattern-based: it can't see whether input is attacker-controlled, and it can't see logic flaws at all. Broken authorization, the #1 category, is mostly invisible to it. Budget most of your manual time for §4 A01 and A06.

## 3. Verify each candidate: source → sink

For every candidate you intend to report, answer four questions in one line each:

| Question | Example |
|----------|---------|
| **Source**: where does the data enter? | `GET /export?file=` query param |
| **Path**: what touches it on the way? | `views.export()` → `storage.read(name)` |
| **Guard**: is there validation, encoding or authorization in between, and does it hold? | none / `os.path.basename()` (holds) / `replace("../","")` (bypassable with `....//`) |
| **Sink**: what dangerous operation runs? | `open(BASE + name)` |

Outcome:
- Source reaches sink with no holding guard: **confirmed finding**.
- Guard holds: **not a finding**. Drop it; mention it only if the guard is fragile.
- You couldn't trace it (dynamic dispatch, missing code): **unverified**. Report it as 🟡 with "unverified: could not trace X", never as 🔴.

**False-positive traps** (check before reporting):
- Constant strings: `os.system("make clean")` has no input.
- Test files, fixtures, examples, migrations with hard-coded values.
- MD5/SHA-1 used as a non-security checksum or cache key.
- `|safe` / `dangerouslySetInnerHTML` on content already sanitized server-side. Verify the sanitizer is actually an allowlist sanitizer.
- ORM methods that look raw but parameterize (`FromSqlInterpolated`, Prisma tagged templates, `sql\`...\``).

## 4. Category checklist: OWASP Top 10:2025

Each section: what to check → where to look → the fix pattern. Scanner rule IDs are in brackets.

### A01:2025 Broken Access Control
The most common serious flaw, and the hardest for tools to see. SSRF now lives here.

- [ ] **Object-level authorization (IDOR / BOLA)**: every handler that takes an ID loads the object *scoped to the caller* (`WHERE id = ? AND owner_id = ?`, or a policy check after loading). Check reads, updates, deletes **and** list/search/export endpoints.
- [ ] **Function-level authorization**: admin/staff routes check role server-side, not just by hiding the button. Check every HTTP method on the route, not just GET.
- [ ] **Deny by default**: new routes are authenticated unless explicitly made public [BAC-ANONYMOUS].
- [ ] **Property-level authorization**: request bodies can't set `role`, `is_admin`, `owner_id`, `price`, `tenant_id` [BAC-MASS-ASSIGN, BAC-PERMIT-ALL]; responses don't return fields the caller shouldn't see (password hashes, other users' emails).
- [ ] **Multi-tenant isolation**: tenant ID comes from the session/token, never from the request.
- [ ] **Path traversal**: file paths built from input are resolved and confined to a base directory [BAC-PATH-TRAVERSAL, BAC-FILE-INCLUDE].
- [ ] **SSRF**: outbound requests to user-supplied URLs are allowlisted by scheme and host, private/link-local ranges (incl. `169.254.169.254`) are blocked after DNS resolution, and redirects are re-checked [BAC-SSRF].
- [ ] **Open redirect**: redirect targets are relative or allowlisted [BAC-OPEN-REDIRECT].
- [ ] **CSRF**: cookie-authenticated, state-changing requests require a CSRF token or SameSite cookies [BAC-CSRF-DISABLED].
- [ ] **JWT/session claims** are not trusted for authorization unless verified (see A07).

**How to audit it fast:** list every route with its auth requirement in a table (route, method, who may call it, the check in code). Every row with an ID parameter and no ownership check is a finding.

### A02:2025 Security Misconfiguration
- [ ] Debug off in production; no stack traces, SQL errors or framework versions in responses [CFG-DEBUG, CFG-ERROR-LEAK, CFG-STACKTRACE].
- [ ] CORS: exact origins only; never `*` or a reflected Origin together with credentials [CFG-CORS-ANY].
- [ ] Cookies: `Secure`, `HttpOnly`, `SameSite` on auth cookies [CFG-COOKIE-FLAGS].
- [ ] Security headers: `Content-Security-Policy`, `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `frame-ancestors`/`X-Frame-Options`.
- [ ] `ALLOWED_HOSTS` / host validation set [CFG-HOSTS-ANY].
- [ ] Admin consoles, actuator, GraphQL introspection, Swagger UI, debug toolbars not exposed publicly [CFG-ACTUATOR, CFG-GRAPHQL-INTROSPECTION].
- [ ] Default credentials, sample apps, and unused endpoints removed; old API versions retired (API9 inventory).
- [ ] Cloud/IaC: storage buckets not public, least-privilege IAM, no `0.0.0.0/0` on admin ports.
- [ ] XML parsers have external entities disabled [INJ-XXE, INJ-XXE-JAVA].

### A03:2025 Software Supply Chain Failures
- [ ] Every new dependency exists under exactly that name, has credible history, and is needed. Typosquatting/slopsquatting checks are in the [AI-Generated Code Guide](ai-generated-code-review.md).
- [ ] Lockfile committed and consistent with the manifest; no `*`/`latest` versions [SUP-UNPINNED-DEP].
- [ ] Known-vulnerable versions: run `scripts/dep-audit.py` (§2) and report real results; anything in CISA KEV first [DEP-KNOWN-VULN].
- [ ] Single trusted package index; no `--extra-index-url` dependency-confusion setups [SUP-EXTRA-INDEX].
- [ ] CI: third-party actions pinned to a commit SHA; least-privilege `permissions:`; secrets not exposed to fork PRs (`pull_request_target` with checkout of PR code is a 🔴) [SUP-ACTION-UNPINNED].
- [ ] No `curl | sh` installers in build or Dockerfiles [SUP-PIPE-TO-SHELL].
- [ ] ML: model files from pinned revisions; no `trust_remote_code=True` [SUP-TRUST-REMOTE-CODE].

### A04:2025 Cryptographic Failures
- [ ] Passwords: argon2id, bcrypt or scrypt via a library. Never MD5/SHA-x, even salted [CRY-PASSWORD-FAST-HASH].
- [ ] Encryption: AEAD (AES-GCM, ChaCha20-Poly1305), unique nonce per message. No ECB, DES, RC4, or a homemade construction [CRY-WEAK-CIPHER].
- [ ] Integrity/authenticity: HMAC-SHA-256 or signatures; MD5/SHA-1 only for non-security checksums [CRY-WEAK-HASH].
- [ ] Randomness for tokens, IDs, OTPs and resets comes from a CSPRNG [CRY-INSECURE-RANDOM].
- [ ] TLS verification never disabled [CRY-TLS-VERIFY-OFF]; TLS enforced for all external traffic (HSTS).
- [ ] Keys never in source [CRY-PRIVATE-KEY]; loaded from a KMS/secret store; rotation possible.
- [ ] Sensitive data at rest encrypted where required; not cached in browsers or logs.

### A05:2025 Injection
Covers SQL, NoSQL, OS command, LDAP, template (SSTI), expression-language, XPath, header/log injection, and XSS.

- [ ] SQL: parameterized everywhere; identifiers (column/table/sort) come from an allowlist [INJ-SQL-*]. Details: [SQL Injection Guide](cross-cutting/sql-injection-prevention.md).
- [ ] NoSQL: filters built from typed fields; reject `$`-prefixed keys from input [INJ-NOSQL].
- [ ] OS commands: no shell; argument arrays; input never becomes the command [INJ-CMD-*].
- [ ] Code: no `eval`/`exec`/`new Function` on anything input-derived [INJ-CODE-*].
- [ ] Templates: input is a variable, never the template source [INJ-SSTI].
- [ ] XSS: auto-escaping on; every bypass (`|safe`, `v-html`, `dangerouslySetInnerHTML`, `Html.Raw`) justified and sanitized; CSP set [XSS-*]. Details: [XSS Prevention Guide](cross-cutting/xss-prevention.md).
- [ ] Regex from input escaped (ReDoS) [INJ-REGEX].
- [ ] CRLF stripped from anything written into headers or log lines.

### A06:2025 Insecure Design
Flaws in the logic itself; no single line is wrong. Tools find almost none of these.

- [ ] Business-flow abuse: can a step be skipped (pay → ship), replayed (coupon, refund), or raced (two withdrawals of one balance)? Check for idempotency keys and transactional/locked balance updates.
- [ ] Limits: rate limits on login, OTP, password reset, signup, expensive search/export, and LLM calls; maximum page size; upload size and type limits (API4 resource consumption).
- [ ] Sensitive flows protected against automation (API6): purchases, account creation, invites.
- [ ] Trust in client-side checks: any validation, price, or permission computed in the browser and trusted by the server.
- [ ] Missing threat-model controls from §1: every trust boundary has a check on the trusted side.

### A07:2025 Authentication Failures
- [ ] No hard-coded credentials or live tokens [AUTH-CLOUD-TOKEN, AUTH-HARDCODED-SECRET]. A leaked credential is 🔴 and must be **rotated**, not just deleted (it stays in git history).
- [ ] Brute-force protection: rate limiting / lockout / CAPTCHA on login, OTP, and reset.
- [ ] Password policy per NIST 800-63B (length, breached-password check; no forced rotation).
- [ ] Sessions: regenerated on login and privilege change; invalidated on logout and password change; sensible idle/absolute timeouts.
- [ ] JWT: signature verified with an explicit algorithm list; `exp`, `iss` and `aud` checked; no `none`; short expiry; revocation strategy [AUTH-JWT-NONE, AUTH-JWT-DECODE].
- [ ] Secrets and tokens compared in constant time [AUTH-TIMING-COMPARE].
- [ ] Password reset tokens: single-use, short-lived, CSPRNG, bound to the user; no user enumeration in reset/login responses.
- [ ] MFA available for privileged accounts; recovery flow doesn't bypass it.

### A08:2025 Software or Data Integrity Failures
- [ ] No native deserialization of untrusted data: pickle, `yaml.load`, Java `ObjectInputStream`, .NET `BinaryFormatter`, PHP `unserialize`, Ruby `Marshal` [INT-*].
- [ ] ML checkpoints loaded safely (`weights_only=True`, safetensors) [INT-TORCH-LOAD].
- [ ] Webhooks verify signatures (HMAC over the raw body, constant-time compare, timestamp to stop replay).
- [ ] Updates, plugins and CI artifacts verified (signature/checksum) before use.
- [ ] Third-party scripts carry Subresource Integrity or are self-hosted [INT-NO-SRI].
- [ ] Data that drives authorization (cookies, hidden fields, client-side state) is signed or kept server-side.

### A09:2025 Security Logging and Alerting Failures
- [ ] Security events are logged: login success/failure, MFA, password/permission changes, access denials, admin actions, input-validation failures.
- [ ] Logs carry who/what/when/where (user ID, action, resource, source IP, request ID), and **no secrets or excess PII** [LOG-SECRET].
- [ ] Log injection prevented (structured logging, or CR/LF stripped).
- [ ] Alerting exists for attack signals (brute force, spikes in 401/403/5xx), not just log storage.

### A10:2025 Mishandling of Exceptional Conditions
New in 2025. Errors that crash, leak, or quietly **fail open**.

- [ ] **Fail closed**: an exception inside an authorization, signature, validation or payment check denies the action. `except: return True` on a permission check is 🔴 [EXC-FAIL-OPEN].
- [ ] No silently swallowed exceptions on security-relevant paths [EXC-PY-SWALLOW, EXC-EMPTY-CATCH, EXC-GO-EMPTY-ERR, EXC-RUBY-SWALLOW].
- [ ] Partial failures roll back: multi-step writes run in a transaction; no half-applied state after an error.
- [ ] Resource exhaustion handled: timeouts on every outbound call, bounded retries with backoff, bounded queues and payload sizes.
- [ ] Errors returned to clients are generic; details go to logs with a correlation ID.

Details: [Error Handling Guide](cross-cutting/error-handling-principles.md).

## 5. APIs: OWASP API Security Top 10:2023 cross-check

Most API risks are already covered above; use this table to confirm none were skipped.

| API risk | Covered in |
|----------|------------|
| API1 Broken Object Level Authorization | A01 (object-level) |
| API2 Broken Authentication | A07 |
| API3 Broken Object Property Level Authorization | A01 (property-level, mass assignment) |
| API4 Unrestricted Resource Consumption | A06 (limits), A10 (timeouts) |
| API5 Broken Function Level Authorization | A01 (function-level) |
| API6 Unrestricted Access to Sensitive Business Flows | A06 |
| API7 Server Side Request Forgery | A01 (SSRF) |
| API8 Security Misconfiguration | A02 |
| API9 Improper Inventory Management | A02 (old versions, debug endpoints) |
| API10 Unsafe Consumption of APIs | Treat third-party API responses as untrusted input: validate, time out, cap size, don't follow redirects blindly |

GraphQL extra checks: query depth/complexity limits, batching limits, field-level authorization in resolvers, introspection off in production.

## 6. AI features: OWASP Top 10 for LLM Applications 2025

Apply when the code calls an LLM, builds prompts, runs agents/tools, or does retrieval (RAG).

| Risk | What to check |
|------|---------------|
| **LLM01 Prompt Injection** | User text and retrieved documents never go into the system prompt [LLM-SYSTEM-PROMPT-INTERP]; untrusted content is delimited; the design assumes injection *will* succeed and limits what a hijacked model can do |
| **LLM02 Sensitive Information Disclosure** | No secrets, other users' data, or internal data in prompts or context; output filtered for PII where needed |
| **LLM03 Supply Chain** | Models and datasets from pinned, trusted sources; no remote code at load (A03) |
| **LLM04 Data and Model Poisoning** | Training/fine-tune/RAG sources controlled; who can write to the vector store or knowledge base? |
| **LLM05 Improper Output Handling** | Model output is untrusted input: never passed to `eval`, shell, SQL or `innerHTML`; parsed into a schema and validated [LLM-OUTPUT-EXEC] |
| **LLM06 Excessive Agency** | Tools are least-privilege and scoped to the user's own permissions; destructive or external actions need human approval; no code-exec tools without a sandbox [LLM-DANGEROUS-FLAG, LLM-SHELL-TOOL] |
| **LLM07 System Prompt Leakage** | The system prompt holds no secrets or authorization rules; authorization is enforced in code, not by instructions |
| **LLM08 Vector and Embedding Weaknesses** | Retrieval is filtered by the caller's tenant/permissions *before* results reach the model |
| **LLM09 Misinformation** | High-stakes outputs are grounded/cited or human-reviewed; the UI doesn't present guesses as facts |
| **LLM10 Unbounded Consumption** | Per-user rate and token limits, max input/output tokens, timeouts, spend caps |

## 7. Severity

Use the skill's labels; record CVSS-style severity only if the user asks for it.

| Situation | Label |
|-----------|-------|
| Exploitable now by an unauthenticated or low-privilege attacker: injection, auth bypass, IDOR on sensitive data, RCE, leaked live credential, fail-open check | 🔴 `[blocking]` |
| Exploitable only with extra conditions; a missing defense-in-depth layer (CSP, rate limit, header); weak crypto on low-value data; anything you couldn't fully trace | 🟡 `[important]` |
| Hardening with no plausible attack path today | 🟢 `[nit]` |

In a diff review, a pre-existing vulnerability outside the diff is labeled `pre-existing` and capped at 🟡 (diff discipline). In a codebase audit there's no diff, so severity is the risk to the system.

## 8. Report format

Each finding:

```markdown
🔴 **[blocking]** SQL injection in user search — `api/users.py:42`
OWASP: A05:2025 Injection · CWE-89 · Confidence: confirmed
Source → sink: `GET /users?q=` → `search(q)` → `cursor.execute(f"... LIKE '%{q}%'")`, no parameterization.
Why: any visitor can read or modify the whole database (`q=' OR 1=1 --`).
Fix: `cursor.execute("... LIKE %s", (f"%{q}%",))`. Regression test: assert `q="' OR 1=1 --"` returns no rows.
```

End the audit with:
- **OWASP coverage**: one line per category A01–A10 (plus API/LLM if applicable): `checked — N findings` / `checked — none` / `not checked (reason)`. Never leave a category silently out.
- **Top risks**: the three to five findings to fix first, in order.
- **Checks run**: scanner (with counts), dependency audit, tests: real results or "not run (reason)".
- **Out of scope / not verified**: what you couldn't trace or didn't read.

Template: [assets/security-audit-template.md](../assets/security-audit-template.md).

## 9. Hand-off to fixing

Hand each confirmed finding to the [Remediation Playbook](remediation-playbook.md) **one at a time**, highest risk first. The audit report is the work list. Don't start fixing until the report is written, so the full picture survives if the fixing goes wrong.
