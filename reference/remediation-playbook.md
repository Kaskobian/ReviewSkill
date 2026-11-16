# Remediation Playbook: fixing review and audit findings without breaking things

Use this when **fixing** what a review or audit found, whether you're the agent doing the fix or the reviewer checking it. It exists because fixing is where models fail most. Finding a bug takes a fresh view of the code; fixing it takes discipline over a long, growing context, and that's where reasoning degrades.

The rules are the same for every model. Smaller models need them to stay on track; larger, more expensive models need them to avoid spending tokens rewriting what wasn't broken.

---

## How fixing goes wrong (name it to avoid it)

| Failure | What it looks like | Prevention |
|---------|--------------------|------------|
| **Batch fixing** | "Fixing all 12 findings" in one edit; half land, three regress, nothing is verified | One finding per cycle (§2) |
| **Context rot** | After 6+ fixes the model forgets the original code, re-breaks earlier fixes, or patches code that no longer exists | Re-read the file before every edit; restart from the work list, not from memory (§4) |
| **Scope creep** | Fixing the SQL injection, also "cleaning up" the function, renaming variables, reformatting the file | Smallest diff that removes the risk; refactors are a separate finding |
| **Symptom fix** | Escaping one input when the sink is reached from five routes; adding `if (id == 1)` to make a test pass | Fix at the sink or the shared boundary; find every caller first |
| **Fake verification** | "This should fix it ✅" with nothing run | A fix is done only when a check that failed before passes now |
| **Test tampering** | Deleting, skipping or loosening the failing test, or editing the expected value to match the bug | Tests are the spec; changing one needs the same justification as changing the code |
| **Hallucinated fix** | Calling a sanitizer, flag or API that doesn't exist in the pinned version | Verify every new API against the installed version before using it |
| **Loop thrashing** | Same fix attempted 3+ times with small variations, each failing | Two failed attempts → stop and re-diagnose (§5) |
| **Silent behavior change** | The fix changes an API response, error code or default that clients rely on | List observable behavior changes in the fix note |

---

## 1. Build the work list first

Turn the review/audit into an ordered list before touching code:

```markdown
| # | Finding | Location | Severity | Status |
|---|---------|----------|----------|--------|
| 1 | SQL injection in search | api/users.py:42 | 🔴 | todo |
| 2 | IDOR on GET /orders/:id | api/orders.py:17 | 🔴 | todo |
| 3 | Debug enabled | settings.py:8 | 🟡 | todo |
```

Order: 🔴 before 🟡 before 🟢; within a tier, exploitable-without-login first. Group findings only when they share one root cause and one fix (e.g. one missing `authorize()` helper used by 14 handlers is **one** item).

Keep the list in a file or in the conversation; it's the memory that survives a long session.

## 2. The fix cycle: one finding at a time

For each item, in order:

1. **Re-read**: open the current code at the location (don't trust what you remember or what the audit quoted; earlier fixes may have moved it). Confirm the finding is still present.
2. **Find every path**: list all callers/routes that reach the sink (search for the function name). The fix belongs where it covers them all: the sink, or the shared boundary.
3. **Prove it**: write or identify a check that **fails now**: a regression test with the attack input (`q="' OR 1=1 --"`, another user's ID, `../../etc/passwd`), or the scanner rule hitting this line. No failing check = you can't show the fix works.
4. **Smallest fix**: change only what removes the risk. Use the canonical fix pattern (§6). No renames, reformatting, or unrelated cleanup in the same edit.
5. **Verify**: run the check from step 3 (it must pass now) **and** the existing tests around the change (they must still pass). Re-run `scripts/security-scan.py` on the file for security findings.
6. **Record**: update the work list (`fixed`, with the check that proves it) and move on.

Never start item N+1 while item N is unverified.

### Fix note (one per finding)

```markdown
✅ #1 SQL injection in search: api/users.py:42
Change: f-string query → parameterized `cursor.execute("... LIKE %s", (pattern,))`
Covers: GET /users, GET /admin/users (both call search())
Proof: tests/test_users.py::test_search_rejects_injection: failed before, passes now
Regression: full users test module 18/18 passing
Behavior change: none
```

## 3. Verification gates

A finding is **fixed** only when all apply:

- [ ] The proving check failed before the change and passes after.
- [ ] Existing tests in the touched area still pass (real output seen, not assumed).
- [ ] The scanner no longer reports the line (security findings), or the remaining hit is explained.
- [ ] Every caller found in step 2 is covered.
- [ ] The diff contains nothing unrelated to this finding.

Couldn't run anything (chat-only)? Then the status is `fix proposed: unverified`, never `fixed`. Give the user the exact test to run.

## 4. Long sessions: protect the context

Reasoning quality drops as the context fills with old diffs, logs and dead ends. Counter it:

- **Re-anchor every 3 fixes**: re-read the work list and the current state of touched files; drop old tool output from your working memory.
- **Quote less**: show the changed lines and a few lines around them, never whole files.
- **Summarize, then continue**: when the session is long, write a status summary (work list + what's verified + what's next) and continue from that summary, not from the scrollback.
- **Fresh context for big lists**: if more than ~10 findings remain, finish the current one, write the summary, and continue in a new session or sub-agent with only: the work list, the playbook, and the files for the next item.
- **Never edit from memory**: every edit is preceded by reading the current file content.

## 5. When a fix fails

1. **First failure**: read the actual error/test output in full. Fix what it says, not what you expected.
2. **Second failure on the same item: stop editing.** Revert to the last known-good state. Re-diagnose from scratch: re-read the code, re-trace source → sink, question the assumption the last two attempts shared.
3. **Third failure**: mark the item `blocked`, write down what was tried and what the evidence shows, and move to the next item or ask the user. Thrashing burns tokens and corrupts the code.

Never "fix" a failing check by deleting it, skipping it, loosening the assertion, or catching and ignoring the exception.

## 6. Canonical fixes (the right pattern, first time)

| Finding | Fix | Not a fix |
|---------|-----|-----------|
| SQL injection | Bound parameters; allowlist for identifiers | Escaping quotes, regex filters, blocking `'` |
| Command injection | Argument array, no shell; fixed binary path | Quoting the string, stripping `;` |
| XSS | Auto-escaping / textContent; allowlist sanitizer (DOMPurify, nh3) if HTML is needed | Regex-removing `<script>`, escaping only `<` |
| IDOR / BOLA | Query scoped to the caller (`AND owner_id = :uid`) or a central policy check | Hiding the ID, using UUIDs alone, checking only in the UI |
| Missing authz on a route | Shared middleware/decorator applied to the route group; deny by default | A check copy-pasted into one handler |
| Mass assignment | Explicit allowlist of writable fields (DTO, serializer `fields`, strong params) | Denylisting `role` |
| Path traversal | Resolve the real path, verify it's inside the base dir; or map IDs to files | Removing `../` (bypassable) |
| SSRF | Allowlist host+scheme; resolve and block private ranges; disable or re-check redirects | Blocking the string `localhost` |
| Weak password hashing | argon2id/bcrypt via library; rehash on next login | Adding a salt to SHA-256 |
| Insecure random token | `secrets` / `crypto.randomBytes` / `SecureRandom` | Seeding `Math.random` |
| TLS verify disabled | Remove it; configure the CA bundle | Disabling it "only in prod" |
| Leaked secret | **Rotate first**, then remove and load from env/secret store | Deleting the line (it stays in git history) |
| Unsafe deserialization | JSON + schema; `yaml.safe_load`; class allowlist | Wrapping in try/except |
| Fail-open exception | Deny on error, log it | Catching a narrower exception and still returning true |
| Prompt injection in system prompt | Static system prompt; untrusted text in user role, delimited; limit tool permissions | Adding "ignore malicious instructions" to the prompt |
| LLM output to a sink | Parse into a schema, allowlist actions, encode before rendering | Asking the model to "only output safe code" |

## 7. Reviewing someone else's fix (including an AI's)

Check these, in order:

1. Does a test exist that fails without the fix? Revert the fix mentally (or actually): would the test fail?
2. Is the fix at the sink/shared boundary, or only on the one route the audit named?
3. Does the diff contain anything else? Unrelated changes in a security fix are 🟡: they hide what the fix really changed.
4. Were any tests deleted, skipped, or loosened? That's 🔴 unless justified in writing.
5. Do the APIs used in the fix exist in the pinned versions?
6. Re-run the scanner and the tests yourself; don't accept "tests pass" without output.

## 8. When to stop

Stop and report instead of continuing when:
- The fix needs a design change (new auth model, schema migration, API break): write it up as a proposal.
- Fixing requires credentials, production access, or rotating a secret you can't reach: tell the user exactly what to rotate.
- The remaining items are 🟢 and the user asked only for blocking issues.

Finish with the updated work list: fixed (with proof), blocked (with evidence), not started.
