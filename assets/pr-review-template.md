# PR Review Template

Copy and use this template for your code reviews.

---

## Summary

[Brief overview of what was reviewed - 1-2 sentences]

**PR Size:** [Small/Medium/Large] (~X lines)

## Strengths

- [What was done well]
- [Good patterns or approaches used]
- [Improvements from previous code]

## Architecture & Performance

**Architecture Assessment**
- [ ] Separation of concerns — are responsibilities clearly divided?
- [ ] Module responsibilities — does each module have a single purpose?
- [ ] Dependency direction — do dependencies flow toward stability?
- [ ] Consistent with existing patterns and conventions

> See [Architecture Review Guide](../reference/architecture-review-guide.md) for detailed SOLID, anti-pattern, and coupling analysis.

**Performance Assessment**
- [ ] Algorithm complexity — any O(n²) or worse on large inputs?
- [ ] Memory impact — large allocations, leaks, unbounded growth?
- [ ] I/O impact — excessive API calls, unbatched writes, missing caching?
- [ ] Database queries — N+1 risks, missing indexes, unoptimized joins?

> See [Performance Review Guide](../reference/performance-review-guide.md) for comprehensive Web Vitals, N+1, and caching guidance.

## Required Changes

🔴 **[blocking]** [Short title] — `path/file.ext:123`
What: [the concrete problem]
Why: [the impact if it ships]
Fix: [suggested change, code snippet when useful]

## Important Suggestions

🟡 **[important]** [Short title] — `path/file.ext:123`
What: [the concrete problem]
Why: [why this matters]
Fix: [suggested approach]

## Minor Suggestions

🟢 **[nit]** [Minor improvement suggestion]

💡 **[suggestion]** [Alternative approach to consider]

## Learning Notes

📚 [Educational context worth sharing about X]

📚 [Background behind design decision Y]

## Security Considerations

- [ ] No hardcoded secrets
- [ ] Input validation present
- [ ] Authorization checks in place
- [ ] No SQL/XSS injection risks
- [ ] CSRF protection for state-changing operations
- [ ] Sensitive data not leaked in logs/errors
- [ ] Dependency vulnerabilities checked (npm audit / pip audit / cargo audit)
- [ ] `scripts/security-scan.py --diff` run; each candidate verified or dismissed
- [ ] Confirmed security findings tagged with OWASP category + CWE (e.g. `A05:2025 Injection · CWE-89`)

> See [Security Review Guide](../reference/security-review-guide.md) for the per-change checklist, or [OWASP Security Audit](../reference/owasp-security-audit.md) for a full A01–A10 audit.

## Test Coverage

- [ ] Unit tests added/updated
- [ ] Edge cases covered
- [ ] Error cases tested
- [ ] Tests have teeth: would fail if the core logic broke (see [Test Quality Guide](../reference/test-quality-review.md))

## Verification

- [ ] Tests run: [command + actual result, or "not run — reason"]
- [ ] Lint / type checks run: [actual result, or "not run — reason"]
- [ ] New dependencies verified: exist on registry, maintained, license compatible (see [AI-Generated Code Guide](../reference/ai-generated-code-review.md))

> Report a check as passing only after seeing it pass. When checks were not run, the verdict rests on static review — say so.

## Verdict

**[ ] ✅ Approve** - Ready to merge
**[ ] 💬 Comment** - Minor suggestions, can merge
**[ ] 🔄 Request Changes** - Must address blocking issues

---

## Quick Copy Templates

### Blocking Issue
```
🔴 **[blocking]** [Title] — `file.ts:123`
What: [the concrete problem]
Why: [the impact if it ships]
Fix:
\`\`\`typescript
// Your suggested code
\`\`\`
```

### Important Suggestion
```
🟡 **[important]** [Title]

[Why this is important]

**Consider:**
- Option A: [description]
- Option B: [description]
```

### Minor Suggestion
```
🟢 **[nit]** [Suggestion]

Not blocking, but consider [improvement].
```

### Praise
```
🎉 **[praise]** Great work on [specific thing]!

[Why this is good]
```

### Learning
```
📚 **[learning]** [Educational note]

For context, [X] works this way because [Y]. No action needed — just sharing.
```
