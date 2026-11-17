# Contributing to AI Code Review Guide

Thank you for your interest in contributing! This document provides guidelines for contributing to this code review skill project.

## Skill Development Standards

This project is a cross-platform Agent Skill (usable in Claude Code, Claude.ai, ChatGPT, Codex, Cursor, GitHub Copilot, Gemini, Windsurf, Cline and any other assistant). Contributors should follow the standards below.

### Directory Structure

```
code-review-skill/
├── SKILL.md                    # Required: main file (always loaded)
├── AGENTS.md                   # Entry point for Codex/Amp/generic agents (source of the agent contract)
├── CLAUDE.md                   # Pointer for Claude Code
├── GEMINI.md                   # Pointer for Gemini CLI
├── .cursorrules                # Pointer for Cursor (legacy)
├── .cursor/rules/code-review.mdc # Pointer for Cursor (rules format)
├── .github/copilot-instructions.md # Pointer for GitHub Copilot
├── .windsurfrules              # Pointer for Windsurf
├── .clinerules                 # Pointer for Cline
├── README.md
├── CONTRIBUTING.md
├── LICENSE
├── adapters/                   # Platform setup + paste-ready instructions
│   ├── README.md               # Per-platform setup guide
│   ├── universal-prompt.md     # Self-contained prompt for assistants with no file access
│   ├── universal-prompt.ru.md  # Russian edition
│   ├── chatgpt-instructions.md # ChatGPT Custom GPT / Project instructions (<8000 chars)
│   ├── chatgpt-instructions.ru.md # Russian edition (<8000 chars)
│   ├── claude-project-instructions.md # Claude.ai Project instructions
│   └── claude-project-instructions.ru.md # Russian edition
├── reference/                  # On-demand language/framework guides
│   ├── react.md                # React 19 / Next.js / TanStack Query v5
│   ├── vue.md                  # Vue 3.5 Composition API
│   ├── angular.md              # Angular 17+, Signals, Standalone, RxJS
│   ├── svelte.md               # Svelte 5 / SvelteKit, runes, SSR boundary
│   ├── rust.md                 # Ownership, async, unsafe, cancellation
│   ├── typescript.md           # Type safety, generics, strict mode
│   ├── nestjs.md               # NestJS DI, modules, Guards/Pipes, DTOs
│   ├── python.md               # Type hints, async, testing
│   ├── django.md               # Django / DRF, N+1, serializers, async views
│   ├── fastapi.md              # FastAPI, Depends, Pydantic v2, async
│   ├── java.md                 # Java 17/21, Spring Boot 3, virtual threads
│   ├── java8.md                # Java 8, Spring Boot 2, javax.*, legacy stack
│   ├── kotlin.md               # Kotlin / Android, coroutines, Flow, Compose
│   ├── swift.md                # Swift 5.9+/6, SwiftUI, concurrency, optionals
│   ├── dart.md                 # Dart / Flutter rebuilds, null safety, isolates, state
│   ├── go.md                   # Error handling, goroutines, context
│   ├── csharp.md               # C# / .NET 8, async, EF Core, ASP.NET Core
│   ├── php.md                  # PHP 8.x, types, PDO, security, Composer
│   ├── ruby.md                 # Ruby 3.4+/4.0, Rails 8.x, Active Record/Job
│   ├── c.md                    # Memory safety, UB, error handling
│   ├── cpp.md                  # RAII, move semantics, exception safety
│   ├── zig.md                  # Allocators, error unions, comptime, C interop
│   ├── qt.md                   # Object model, signals/slots, GUI perf
│   ├── css-less-sass.md        # Variables, responsive, performance
│   ├── architecture-review-guide.md  # SOLID, anti-patterns, coupling
│   ├── performance-review-guide.md   # Web Vitals, N+1, complexity
│   ├── security-review-guide.md      # Per-change security checklist, JWT, validation
│   ├── owasp-security-audit.md       # OWASP Top 10:2025 / API / LLM audit procedure
│   ├── remediation-playbook.md       # Fixing findings one at a time, verification gates
│   ├── common-bugs-checklist.md      # Quick-reference bug patterns
│   ├── code-quality-universal.md      # Language-agnostic quality anti-patterns
│   ├── code-review-best-practices.md # Communication & process
│   ├── test-quality-review.md        # Test teeth, flakiness, over-mocking, coverage
│   ├── ai-generated-code-review.md   # Hallucinated APIs, slopsquatting, test mirroring
│   └── cross-cutting/               # Language-agnostic cross-cutting patterns
│       ├── sql-injection-prevention.md # Parameterized queries, 6 languages
│       ├── xss-prevention.md           # Output encoding, CSP, 5 frameworks
│       ├── n-plus-one-queries.md       # N+1 queries, eager loading, 5 languages
│       ├── error-handling-principles.md # Error handling principles, 7 languages
│       └── async-concurrency-patterns.md # Concurrency patterns, 7 languages
├── assets/                     # Templates and quick reference
│   ├── review-checklist.md
│   ├── pr-review-template.md
│   └── security-audit-template.md    # OWASP audit report + remediation work list
└── scripts/
    ├── pr-analyzer.py          # PR complexity analyzer (--json, --stats, --no-emoji)
    ├── test_pr_analyzer.py     # Analyzer unit tests (stdlib unittest)
    ├── security-scan.py        # OWASP/CWE-mapped security scanner
    ├── test_security_scan.py   # Scanner unit tests: positive + false-positive case per rule
    ├── dep-audit.py            # Known-vulnerable dependencies (OSV + CISA KEV + NVD)
    ├── test_dep_audit.py       # Dependency audit tests (offline, canned API responses)
    └── validate_skill.py       # Package self-check — run before every submit
```

### Frontmatter Standards

SKILL.md must include YAML frontmatter:

```yaml
---
name: skill-name
description: |
  What it does. When it triggers.
  Use when [specific use cases].
allowed-tools: ["Read", "Grep", "Glob"]  # Optional: restrict tool access
---
```

#### Required Fields

| Field | Description | Constraints |
|------|------|------|
| `name` | Skill identifier | Lowercase letters, digits, hyphens; max 64 characters |
| `description` | Capabilities and activation conditions | Max 1024 characters; must include "Use when" |

#### Optional Fields

| Field | Description | Example |
|------|------|------|
| `allowed-tools` | Restricts tool access (recognized only by Claude Code, ignored elsewhere; this skill does not use it, to stay cross-platform) | `["Read", "Grep", "Glob"]` |

### Naming Conventions

**Skill name rules**:
- Use only lowercase letters, digits and hyphens (kebab-case)
- Max 64 characters
- No underscores or uppercase letters

```
✅ Correct: code-review-skill, typescript-advanced-types
❌ Wrong: CodeReview, code_review, TYPESCRIPT
```

**File naming rules**:
- Reference files are lowercase: `react.md`, `vue.md`
- Multi-word files use hyphens: `common-bugs-checklist.md`

### Writing the Description

The description must have two parts:

1. **Capability statement**: what the Skill does, concretely
2. **Trigger conditions**: start with "Use when" and say when it activates

```yaml
# ✅ Good example
description: |
  Provides comprehensive code review guidance for React 19, Vue 3, Rust,
  TypeScript, Java, Python, and C/C++.
  Helps catch bugs, improve code quality, and give constructive feedback.
  Use when reviewing pull requests, conducting PR reviews, establishing
  review standards, or mentoring developers through code reviews.

# ❌ Bad example (too vague, no trigger conditions)
description: |
  Helps with code review.
```

### Progressive Disclosure

The agent loads supporting files only when needed, never everything at once. In chat environments that cannot read files (such as ChatGPT without uploaded knowledge files), the adapter instructions tell the model to state which guide is missing and continue with the core process.

#### File Responsibilities

| File | When loaded | Content |
|------|----------|------|
| `SKILL.md` | Always | Core principles, quick index, when to use |
| `reference/*.md` | On demand | Detailed language/framework guides |
| `assets/*.md` | When explicitly needed | Templates, checklists |
| `scripts/*.py` | When explicitly directed | Utility scripts |

#### Content Organization

**SKILL.md** (under ~300 lines):
- Summary: 2-3 sentences on its purpose
- Core principles and methodology
- Language/framework index tables (linking to reference/)
- When to use this Skill

**reference/*.md** (detailed content):
- Complete code examples
- All best practices
- Review Checklist
- Edge cases and pitfalls

### File References

When referencing other files from SKILL.md:

```markdown
# ✅ Correct: use Markdown links
| **React** | [React Guide](reference/react.md) | Hooks, React 19, RSC |
| **Vue 3** | [Vue Guide](reference/vue.md) | Composition API |

See [React Guide](reference/react.md) for the full guide.

# ❌ Wrong: use code formatting
See the `reference/react.md` file.
```

**Path rules**:
- Use relative paths (relative to the Skill directory)
- Use forward slashes `/`, not backslashes
- No `./` prefix

### Conventions

**Severity**: review comments use the labeling scheme from "Technique 4" in SKILL.md, three levels from red to green by priority:

- 🔴 `[blocking]` - Must fix before merge
- 🟡 `[important]` - Should fix; open to discussion
- 🟢 `[nit]` - Optional improvement; does not block merge

New reference guides must use these labels; do not invent equivalent names (such as critical/warning/suggestion).

**Language policy**: the guides, README and landing page are written in English. Write all new and changed content in English. The README has English and Russian sections; the adapters have English and Russian (`.ru.md`) editions, which must be kept in sync when changed. All adapters tell the model to write the review in the language the user asks in.

---

## Types of Contributions

### Adding a New Language

1. Create a new file in `reference/` (such as `go.md`)
2. Follow this structure:

```markdown
# [Language] Code Review Guide

> Short description: one sentence on what it covers.

## Table of Contents
- [Topic 1](#topic-1)
- [Topic 2](#topic-2)
- [Review Checklist](#review-checklist)

---

## Topic 1

### Subtopic

```[language]
// ❌ Bad pattern - explain why it is bad
bad_code_example()

// ✅ Good pattern - explain why it is good
good_code_example()
```

---

## Review Checklist

### Category 1
- [ ] Check item 1
- [ ] Check item 2
```

3. Add a link in the `SKILL.md` index table
4. Update the statistics in `README.md`

**Index sync (required)**: the list of guides is repeated in four places. When adding or removing a guide, update all of them to avoid drift:

1. The `SKILL.md` index tables
2. The language table and repository tree in `README.md` (the Russian section reuses the English tree; only its language table needs syncing)
3. The directory tree in `CONTRIBUTING.md` (this file)
4. The LANGUAGES block in `index.html` (`index.en.html` only redirects to it)

If you change the core process or severity labels, also update `adapters/chatgpt-instructions.md`, `adapters/claude-project-instructions.md` and their Russian editions (`.ru.md`). Each ChatGPT adapter (including the Russian one) must stay under 8000 characters.

### Adding Framework Patterns

1. Cite the official documentation
2. Include version numbers (such as "React 19", "Vue 3.5+")
3. Provide runnable code examples
4. Add matching checklist items

### Improving Existing Content

- Fix spelling or grammar errors
- Update outdated patterns (note the version change)
- Add edge-case examples
- Make code examples clearer

---

## Code Example Standards

### Format

```markdown
// ❌ Problem - explain why this is bad
problematic_code()

// ✅ Recommended - explain why this is better
recommended_code()
```

### Quality Bar

- Base examples on real scenarios, not contrived ones
- Show both the problem and the fix
- Keep examples short and focused
- Include the necessary context (imports and so on)

---

## Submission Process

### Reporting Issues

- Report issues or suggestions to the project maintainers
- Give a clear description and examples
- Name the language/framework involved

### Making Changes

1. Create a feature branch: `git checkout -b feature/add-go-support`
2. Make your changes
3. Run `python scripts/validate_skill.py` — it checks structure, link integrity, per-platform entry points, adapter character limits, and runs `scripts/test_pr_analyzer.py`. All checks must pass before the change is submitted.
4. Commit (see the commit format below)
5. Submit the change for maintainer review in whatever way the project is hosted (pull request or patch)

### Adding a security-scan rule

Each rule in `scripts/security-scan.py` maps to one OWASP category and one CWE, and carries a `verify` question and a `fix` line. Before adding one:

1. Add a positive test (the vulnerable line is flagged) **and** a negative test for the most common lookalike (the safe line is not flagged) in `scripts/test_security_scan.py`.
2. Run the scanner on a real, well-maintained codebase (e.g. Flask or Express) and look at what it flags. A rule that floods real code with false positives does more harm than good: lower its confidence or tighten it.
3. Keep rules scoped to file types (`exts=`), so a Python pattern never fires on JavaScript.
4. Logic flaws (authorization, business rules, A06 Insecure Design) belong in `reference/owasp-security-audit.md`, not in regexes.

### Keeping platform support intact

The skill must work for any agent. When you change the review process itself, update every surface that states it:

- `SKILL.md` — the source of truth
- `AGENTS.md` — the agent entry contract
- `adapters/universal-prompt.md` (+ `.ru.md`) — the self-contained edition for assistants with no file access
- `adapters/chatgpt-instructions.md` (+ `.ru.md`) — must stay under 8,000 characters
- `adapters/claude-project-instructions.md` (+ `.ru.md`)

Platform pointer files (`CLAUDE.md`, `GEMINI.md`, `.cursorrules`, `.cursor/rules/code-review.mdc`, `.github/copilot-instructions.md`, `.windsurfrules`, `.clinerules`) deliberately contain no process detail — they point at `AGENTS.md`, so they only need touching when a new platform is added. Never make a guide, script, or adapter depend on one vendor's features: the skill is plain Markdown plus a stdlib-only Python script on purpose.

### Commit Message Format

```
type: short description

Details (if needed)

- Specific change 1
- Specific change 2
```

**Types**:
- `feat`: new feature or content
- `fix`: bug fix
- `docs`: documentation-only change
- `refactor`: refactoring (no behavior change)
- `chore`: maintenance work

**Example**:
```
feat: add Go code review guide

- Add reference/go.md
- Cover error handling, concurrency, interface design
- Update SKILL.md index table
```

---

## Skill Design Principles

### Single Responsibility

Each Skill focuses on one core capability. This Skill focuses on **code review** and should not expand into:
- Code generation
- Project scaffolding
- Deployment configuration

### Versioning

- Note framework/language versions in reference files
- Describe version changes in the commit when updating
- Update outdated content rather than deleting it (unless it is fully obsolete)

### Content Quality

- Every recommendation needs a basis (official docs, established best practices)
- Avoid subjective preferences (such as code style); focus on objective problems
- Prioritize common pitfalls and security issues

---

## FAQ

### Q: How do I test my changes?

Verify on the platform you use (full instructions in `adapters/README.md`):

- **Claude Code**: copy the modified Skill into `~/.claude/skills/` and test:
  ```bash
  cp -r code-review-skill ~/.claude/skills/code-review-skill
  ```
- **ChatGPT / Claude.ai**: update the GPT/Project instructions and knowledge files, then compare review output on the same sample code.
- **Smoke test**: ask for a review of `def last(xs): return xs[len(xs)]`. A passing review flags the out-of-bounds index (every call raises `IndexError`), uses severity labels and gives a clear verdict.

### Q: Should I update SKILL.md or a reference file?

- **SKILL.md**: only for the index tables or core principles
- **reference/*.md**: to add or update specific language or framework content

### Q: How do I handle outdated content?

1. Note the version change (such as "React 18 → React 19")
2. Keep the old-version content (if people still use it)
3. Update the related checklist items

---

## Questions

If you have any questions, feel free to ask the project maintainers.
