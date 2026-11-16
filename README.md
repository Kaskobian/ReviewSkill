<div align="center">

<h1>&#128269; Code Review Skill</h1>

<p>
  <strong>A comprehensive, modular code review skill for AI coding agents - Claude, ChatGPT, and others</strong><br/>
</p>

<p>
  <a href="#english">English</a>
  &middot;
  <a href="#russian">Русский</a>
  &middot;
  <a href="./CONTRIBUTING.md">Contributing</a>
</p>

<p>
  <strong>Author/Coder: Kaskobian</strong>
</p>

</div>

---

<a name="english"></a>

## English

### What is this?

**Code Review Skill** is a production-ready skill for AI coding agents - **Claude (Code and Claude.ai), ChatGPT (Custom GPTs and Projects), Codex, Cursor, GitHub Copilot, Gemini, Windsurf, Cline, and any other assistant** - that transforms AI-assisted code review from vague suggestions into a **structured, consistent, and expert-level** process.

It covers **20+ languages and frameworks** with over **21,000 lines** of carefully curated review guidelines - loaded progressively to minimize context window usage.

---

### &#10024; Key Features

- **Cross-Platform** - One skill, any agent: paste-ready adapters for ChatGPT and Claude.ai Projects, native skill install for Claude Code, and conventional entry files for Codex, Cursor, Copilot, Gemini CLI, Windsurf and Cline. A self-contained [universal prompt](adapters/universal-prompt.md) covers assistants with no file access. See [adapters/README.md](adapters/README.md).
- **Progressive Disclosure** - Core skill is ~310 lines; language guides (~200–1,100 lines each) load only when needed.
- **Self-Validating** - `python scripts/validate_skill.py` checks structure, link integrity, per-platform entry points, adapter character limits, and runs the script test suite.
- **Four-Phase Review Process** - Structured workflow from understanding scope to delivering clear feedback.
- **Severity Labeling** - Every finding is categorized: `blocking` · `important` · `nit` · `suggestion` · `learning` · `praise`
- **Output Contract** - Every finding carries location, impact, and a concrete fix; every review ends with a verdict and the checks actually run.
- **Verification Gate** - Run tests/linters before the verdict when the environment allows; report honestly when they were not run.
- **Security-First** - Dedicated security checklists per language ecosystem.
- **OWASP Security Audits** - Full audit procedure mapped to OWASP Top 10:2025, API Security Top 10:2023 and LLM Top 10:2025. Every finding carries an OWASP category and CWE, plus a per-category coverage report. Backed by `scripts/security-scan.py`, a stdlib-only scanner with 70+ OWASP/CWE-mapped rules across 10 languages.
- **Safe Fixing** - A [remediation playbook](reference/remediation-playbook.md) for applying fixes one verified finding at a time. It targets the ways models break code while fixing: batch edits, context rot, test tampering, and retry loops.
- **Token-Efficient** - Scan first, read only what the tools point at, load one guide at a time, group repeated findings. Fewer tokens and better accuracy on any model.
- **AI-Code Aware** - Dedicated guide for hallucinated APIs, dependency typosquatting/slopsquatting, and test mirroring in AI-generated code.
- **Test Quality Review** - Tests reviewed as critically as code: teeth, flakiness, over-mocking, coverage vs confidence.
- **Collaborative Tone** - Questions over commands, suggestions over mandates.
- **Git Hooks** - [`review-hooks/`](review-hooks/README.md): `commit-msg` and `pre-push` hooks that check branch names, commit messages and secrets with plain code (no AI), plus an optional, isolated AI review that can be advisory or required. Tested on Windows and Linux.
- **Automation Awareness** - Clearly separates what human review should catch vs. what linters handle.

---

### &#127760; Supported Languages & Frameworks

<table>
  <thead>
    <tr>
      <th>Category</th>
      <th>Technology</th>
      <th>Guide</th>
      <th>Lines</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td rowspan="6"><strong>Frontend</strong></td>
      <td>&#9883;&#65039; React 19 / Next.js / TanStack Query v5</td>
      <td><code>reference/react.md</code></td>
      <td>~870</td>
    </tr>
    <tr>
      <td>&#128154; Vue 3.5 + Composition API</td>
      <td><code>reference/vue.md</code></td>
      <td>~920</td>
    </tr>
    <tr>
      <td>&#128302; Angular 17+ / Signals / Zoneless</td>
      <td><code>reference/angular.md</code></td>
      <td>~770</td>
    </tr>
    <tr>
      <td>&#128293; Svelte 5 / SvelteKit</td>
      <td><code>reference/svelte.md</code></td>
      <td>~1,060</td>
    </tr>
    <tr>
      <td>&#127912; CSS / Less / Sass</td>
      <td><code>reference/css-less-sass.md</code></td>
      <td>~660</td>
    </tr>
    <tr>
      <td>&#128311; TypeScript</td>
      <td><code>reference/typescript.md</code></td>
      <td>~1,020</td>
    </tr>
    <tr>
      <td rowspan="11"><strong>Backend</strong></td>
      <td>&#9749; Java 17/21 + Spring Boot 3</td>
      <td><code>reference/java.md</code></td>
      <td>~410</td>
    </tr>
    <tr>
      <td>&#9749; Java 8 + Spring Boot 2</td>
      <td><code>reference/java8.md</code></td>
      <td>~580</td>
    </tr>
    <tr>
      <td>&#9889; FastAPI</td>
      <td><code>reference/fastapi.md</code></td>
      <td>~590</td>
    </tr>
    <tr>
      <td>PHP 8.x</td>
      <td><code>reference/php.md</code></td>
      <td>~700</td>
    </tr>
    <tr>
      <td>&#128142; Ruby 3.4+/4.0 + Rails 8.x</td>
      <td><code>reference/ruby.md</code></td>
      <td>~960</td>
    </tr>
    <tr>
      <td>&#128230; NestJS</td>
      <td><code>reference/nestjs.md</code></td>
      <td>~590</td>
    </tr>
    <tr>
      <td>&#128013; Django / DRF</td>
      <td><code>reference/django.md</code></td>
      <td>~1,030</td>
    </tr>
    <tr>
      <td>&#128057; Go</td>
      <td><code>reference/go.md</code></td>
      <td>~990</td>
    </tr>
    <tr>
      <td>&#129408; Rust</td>
      <td><code>reference/rust.md</code></td>
      <td>~840</td>
    </tr>
    <tr>
      <td>&#128187; C# / .NET 8</td>
      <td><code>reference/csharp.md</code></td>
      <td>~520</td>
    </tr>
    <tr>
      <td>&#128013; Python</td>
      <td><code>reference/python.md</code></td>
      <td>~1,070</td>
    </tr>
    <tr>
      <td rowspan="7"><strong>Mobile / Systems</strong></td>
      <td>&#128241; Kotlin / Android</td>
      <td><code>reference/kotlin.md</code></td>
      <td>~1,020</td>
    </tr>
    <tr>
      <td>&#127822; Swift / SwiftUI</td>
      <td><code>reference/swift.md</code></td>
      <td>~930</td>
    </tr>
    <tr>
      <td>&#127919; Dart / Flutter</td>
      <td><code>reference/dart.md</code></td>
      <td>~670</td>
    </tr>
    <tr>
      <td>&#9881;&#65039; C</td>
      <td><code>reference/c.md</code></td>
      <td>~890</td>
    </tr>
    <tr>
      <td>&#128297; C++</td>
      <td><code>reference/cpp.md</code></td>
      <td>~890</td>
    </tr>
    <tr>
      <td>&#9889; Zig</td>
      <td><code>reference/zig.md</code></td>
      <td>~440</td>
    </tr>
    <tr>
      <td>&#128421;&#65039; Qt Framework</td>
      <td><code>reference/qt.md</code></td>
      <td>~760</td>
    </tr>
    <tr>
      <td rowspan="13"><strong>Cross-Cutting</strong></td>
      <td>&#127963;&#65039; Architecture Design Review</td>
      <td><code>reference/architecture-review-guide.md</code></td>
      <td>~470</td>
    </tr>
    <tr>
      <td>&#9889; Performance Review</td>
      <td><code>reference/performance-review-guide.md</code></td>
      <td>~820</td>
    </tr>
    <tr>
      <td>&#128269; Universal Quality Anti-Patterns</td>
      <td><code>reference/code-quality-universal.md</code></td>
      <td>~490</td>
    </tr>
    <tr>
      <td>&#128737;&#65039; Security Review</td>
      <td><code>reference/security-review-guide.md</code></td>
      <td>~510</td>
    </tr>
    <tr>
      <td>&#128272; OWASP Security Audit (Top 10:2025, API, LLM)</td>
      <td><code>reference/owasp-security-audit.md</code></td>
      <td>~250</td>
    </tr>
    <tr>
      <td>&#128295; Remediation Playbook (fixing findings)</td>
      <td><code>reference/remediation-playbook.md</code></td>
      <td>~130</td>
    </tr>
    <tr>
      <td>&#129514; Test Quality Review</td>
      <td><code>reference/test-quality-review.md</code></td>
      <td>~220</td>
    </tr>
    <tr>
      <td>&#129302; AI-Generated Code Review</td>
      <td><code>reference/ai-generated-code-review.md</code></td>
      <td>~260</td>
    </tr>
    <tr>
      <td>&#128200; N+1 Queries</td>
      <td><code>reference/cross-cutting/n-plus-one-queries.md</code></td>
      <td>~310</td>
    </tr>
    <tr>
      <td>&#9888;&#65039; Error Handling Principles</td>
      <td><code>reference/cross-cutting/error-handling-principles.md</code></td>
      <td>~490</td>
    </tr>
    <tr>
      <td>&#9889; Async &amp; Concurrency Patterns</td>
      <td><code>reference/cross-cutting/async-concurrency-patterns.md</code></td>
      <td>~540</td>
    </tr>
    <tr>
      <td>&#128737;&#65039; SQL Injection Prevention</td>
      <td><code>reference/cross-cutting/sql-injection-prevention.md</code></td>
      <td>~310</td>
    </tr>
    <tr>
      <td>&#128737;&#65039; XSS Prevention</td>
      <td><code>reference/cross-cutting/xss-prevention.md</code></td>
      <td>~260</td>
    </tr>
  </tbody>
</table>

---

### &#128260; The Four-Phase Review Process

```
Phase 1 - Context Gathering
  Understand PR scope, linked issues, and intent
                    |
                    v
Phase 2 - High-Level Review
  Architecture - Performance impact - Test strategy
                    |
                    v
Phase 3 - Line-by-Line Analysis
  Logic - Security - Maintainability - Edge cases
                    |
                    v
Phase 4 - Verification, Summary & Decision
  Run tests/lint - Structured feedback - Verdict - Action items
```

---

### &#127991;&#65039; Severity Labels

| Label | Meaning |
|-------|---------|
| &#128308; `blocking` | Must be fixed before merge |
| &#128993; `important` | Should be fixed; discuss if you disagree |
| &#128994; `nit` | Minor style or preference issue; non-blocking |
| &#128161; `suggestion` | Optional improvement worth considering |
| &#128218; `learning` | Educational note for the author |
| &#127881; `praise` | Explicitly highlight great work |

Only 🔴 `blocking` holds a merge. 🔴 / 🟡 / 🟢 are the three severity tiers; the rest are non-blocking annotations. Labels stay in English in every response language so tooling can parse them.

---

### &#128193; Repository Structure

```
code-review-skill/
|
+-- SKILL.md                              # Core skill - loaded on activation (~310 lines)
+-- AGENTS.md                             # Entry point for Codex/Amp/generic agents
+-- CLAUDE.md                             # Entry point for Claude Code
+-- GEMINI.md                             # Entry point for Gemini CLI
+-- .cursorrules                          # Entry point for Cursor (legacy format)
+-- .cursor/rules/code-review.mdc         # Entry point for Cursor (rules format)
+-- .github/copilot-instructions.md       # Entry point for GitHub Copilot
+-- .windsurfrules                        # Entry point for Windsurf
+-- .clinerules                           # Entry point for Cline
+-- README.md
+-- LICENSE
+-- CONTRIBUTING.md
|
+-- adapters/                             # Platform setup + paste-ready instructions
|   +-- README.md                         # Setup for every supported platform
|   +-- universal-prompt.md               # Self-contained prompt, no file access needed
|   +-- universal-prompt.ru.md            # Russian edition
|   +-- chatgpt-instructions.md           # Custom GPT / Project instructions (<8000 chars)
|   +-- chatgpt-instructions.ru.md        # Russian edition (<8000 chars)
|   +-- claude-project-instructions.md    # Claude.ai Project instructions
|   +-- claude-project-instructions.ru.md # Russian edition
|
+-- reference/                            # On-demand language guides
|   +-- react.md                          # React 19 / Next.js / TanStack Query v5
|   +-- vue.md                            # Vue 3.5 Composition API
|   +-- angular.md                        # Angular 17+ / Signals / Zoneless
|   +-- svelte.md                         # Svelte 5 / SvelteKit
|   +-- rust.md                           # Rust ownership, async/await, unsafe
|   +-- typescript.md                     # TypeScript strict mode, generics, ESLint
|   +-- nestjs.md                         # NestJS DI, Guards, Interceptors, DTOs
|   +-- java.md                           # Java 17/21 & Spring Boot 3
|   +-- java8.md                          # Java 8 & Spring Boot 2 (legacy)
|   +-- php.md                            # PHP 8.x types, PDO, security, Composer
|   +-- ruby.md                           # Ruby 3.4+/4.0, Rails 8.x, Active Record/Job
|   +-- python.md                         # Python async, typing, pytest
|   +-- django.md                         # Django / DRF security, serializers, async
|   +-- fastapi.md                        # FastAPI Depends, Pydantic v2, async, test-driven verification
|   +-- go.md                             # Go goroutines, channels, context, interfaces
|   +-- kotlin.md                         # Kotlin / Android coroutines, Compose, Flow
|   +-- swift.md                          # Swift 5.9+/6, SwiftUI, concurrency, optionals
|   +-- dart.md                           # Dart / Flutter rebuilds, null safety, isolates, state
|   +-- csharp.md                         # C# 12 / .NET 8, EF Core, ASP.NET Core
|   +-- c.md                              # C memory safety, UB, error handling
|   +-- cpp.md                            # C++ RAII, move semantics, exception safety
|   +-- zig.md                            # Zig allocators, errors, comptime, C interop
|   +-- qt.md                             # Qt object model, signals/slots, GUI perf
|   +-- css-less-sass.md                  # CSS/Less/Sass variables, responsive design
|   +-- architecture-review-guide.md      # SOLID, anti-patterns, coupling/cohesion
|   +-- code-quality-universal.md        # Reuse audit, parameter sprawl, TOCTOU, no-op updates
|   +-- performance-review-guide.md       # Core Web Vitals, N+1, memory leaks
|   +-- security-review-guide.md          # Security checklist (all languages)
|   +-- owasp-security-audit.md           # OWASP Top 10:2025 / API / LLM audit procedure
|   +-- remediation-playbook.md           # Fixing findings safely, one at a time
|   +-- common-bugs-checklist.md          # Language-specific bug patterns
|   +-- code-review-best-practices.md     # Communication & process guidelines
|   +-- test-quality-review.md            # Test teeth, flakiness, over-mocking, coverage
|   +-- ai-generated-code-review.md       # Hallucinated APIs, slopsquatting, test mirroring
|
+-- reference/cross-cutting/             # Language-agnostic cross-cutting patterns
|   +-- sql-injection-prevention.md       # Parameterized queries, 6 languages
|   +-- xss-prevention.md                 # Output encoding, CSP, 5 frameworks
|   +-- n-plus-one-queries.md             # N+1 queries, eager loading, 5 languages
|   +-- error-handling-principles.md      # Error handling principles, 7 languages
|   +-- async-concurrency-patterns.md     # Concurrency patterns, 7 languages
|
+-- assets/
|   +-- review-checklist.md               # Quick reference checklist
|   +-- pr-review-template.md             # PR review comment template
|   +-- security-audit-template.md        # OWASP audit report + remediation work list
|
+-- scripts/
    +-- pr-analyzer.py                    # PR complexity analyzer (--json, --stats, --no-emoji)
    +-- test_pr_analyzer.py               # Unit tests, stdlib only
    +-- security-scan.py                  # OWASP-mapped security scanner (repo or --diff)
    +-- test_security_scan.py             # Scanner unit tests
    +-- validate_skill.py                 # Self-check: structure, links, entry points, limits
```

---

### &#128640; Setup

Full per-platform instructions: [adapters/README.md](adapters/README.md).

**Claude Code** - copy this folder into your skills directory:

```bash
# macOS / Linux
cp -r code-review-skill-main ~/.claude/skills/code-review-skill

# Windows (PowerShell)
Copy-Item -Recurse code-review-skill-main "$env:USERPROFILE\.claude\skills\code-review-skill"
```

**Claude.ai (Projects)** - paste [adapters/claude-project-instructions.md](adapters/claude-project-instructions.md) into the project's custom instructions, then upload `SKILL.md` and the `reference/` guides you need as project knowledge.

**ChatGPT (Custom GPT or Project)** - paste [adapters/chatgpt-instructions.md](adapters/chatgpt-instructions.md) into the Instructions box (fits the 8,000-character limit), then upload `SKILL.md` and the relevant `reference/*.md` guides as Knowledge / project sources.

**Codex, Cursor, Copilot, Windsurf, Cline, Gemini CLI** - keep the folder in the workspace; each platform's conventional entry file (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursorrules`, `.cursor/rules/`, `.github/copilot-instructions.md`, `.windsurfrules`, `.clinerules`) is present and points the agent at `SKILL.md`.

**Any other assistant (Gemini, Grok, DeepSeek, Qwen, Mistral, local models)** - paste [adapters/universal-prompt.md](adapters/universal-prompt.md) (Russian: [universal-prompt.ru.md](adapters/universal-prompt.ru.md)) as a system prompt or first message; it is self-contained and needs no file uploads.

**Any chat assistant** - paste the universal prompt above, or `SKILL.md` plus the guides for your language, then paste the diff.

Verify the install is sound at any time:

```bash
python scripts/validate_skill.py
```

---

### &#128161; Usage

Once set up, ask for a review:

```
Use code-review-skill to review this PR
```

In Claude Code you can also create a custom slash command in `.claude/commands/`:

```markdown
<!-- .claude/commands/review.md -->
Use code-review-skill to perform a thorough review of the changes in this PR.
Focus on: security, performance, and maintainability.
```

In ChatGPT / Claude.ai, paste the diff or file and ask: *"Review this change"* - the configured instructions drive the same four-phase process.

**Example prompts:**

| Prompt | What happens |
|--------|-------------|
| `Review this React component` | Loads `react.md` - checks hooks, Server Components, Suspense patterns |
| `Review this Java PR` | Loads `java.md` - checks virtual threads, JPA, Spring Boot 3 patterns |
| `Review this Java 8 / Spring Boot 2 PR` | Loads `java8.md` - Stream/Optional, java.time, RestTemplate timeouts, javax.* |
| `Review this Flutter widget` | Loads `dart.md` - rebuilds, const, null safety, isolates, Riverpod/Bloc, keys, disposal |
| `Security review of this Go service` | Loads `go.md` + `security-review-guide.md` |
| `Architecture review` | Loads `architecture-review-guide.md` - SOLID, anti-patterns, coupling |
| `Performance review` | Loads `performance-review-guide.md` - Web Vitals, N+1, complexity |
| `OWASP security audit of this repo` | Runs `security-scan.py`, loads `owasp-security-audit.md` - A01–A10 coverage, OWASP + CWE per finding |
| `Fix the findings from the audit` | Loads `remediation-playbook.md` - one finding at a time, each proven by a failing-then-passing check |

---

### &#128300; Highlights by Language

<details>
<summary><strong>&#9883;&#65039; React 19</strong></summary>

- `useActionState` - Unified form state management
- `useFormStatus` - Access parent form status without prop drilling
- `useOptimistic` - Optimistic UI updates with automatic rollback
- Server Components & Server Actions patterns (Next.js 15+)
- Suspense boundary design, Error Boundary integration, streaming SSR
- `use()` Hook for consuming Promises

</details>

<details>
<summary><strong>&#9749; Java & Spring Boot 3</strong></summary>

- **Java 17/21**: Records, Pattern Matching for Switch, Text Blocks, Sealed Classes
- **Virtual Threads** (Project Loom): High-throughput I/O patterns
- **Spring Boot 3**: Constructor injection, `@ConfigurationProperties`, `ProblemDetail`
- **JPA Performance**: Solving N+1, correct `equals`/`hashCode` on Entities

</details>

<details>
<summary><strong>&#9749; Java 8 & Spring Boot 2 (Legacy)</strong></summary>

- **Java 8**: Lambda, Stream/`Collectors`, Optional, `java.time` (no Records / virtual threads)
- **Concurrency**: bounded thread pools, `CompletableFuture` + explicit executors
- **Spring Boot 2**: `javax.*`, constructor injection, `RestTemplate` timeouts
- **JPA / Hibernate 5**: N+1, Entity `equals`/`hashCode`, UTC time mapping pitfalls

</details>

<details>
<summary><strong>&#129408; Rust</strong></summary>

- Ownership patterns and common pitfalls
- `unsafe` code review requirements (mandatory `SAFETY` comments)
- Async/await - avoiding blocking in async context, cancellation safety
- Error handling: `thiserror` for libraries, `anyhow` for applications

</details>

<details>
<summary><strong>&#128057; Go</strong></summary>

- Goroutine lifecycle management and leak prevention
- Channel patterns, select usage
- `context.Context` propagation
- Interface design (accept interfaces, return structs)
- Error wrapping with `%w`

</details>

<details>
<summary><strong>&#9881;&#65039; C / C++</strong></summary>

- **C**: Pointer/buffer safety, undefined behavior, resource cleanup, integer overflow
- **C++**: RAII ownership, Rule of 0/3/5, move semantics, exception safety, `noexcept`
- **Qt**: Object parent/child memory model, thread-safe signal/slot connections, GUI performance

</details>

---

### &#129309; Contributing

Contributions are welcome! See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

**Ideas:**
- New language guides (Elixir, Scala, Lua...)
- Framework-specific guides (Laravel, Spring WebFlux...)
- Additional checklists and templates
- Translations of core documentation

---

### &#128196; License

MIT - see [LICENSE](./LICENSE) · Author/Coder: Kaskobian

---

<a name="russian"></a>

## Русский

### Что это?

**Code Review Skill** - готовый к продакшену навык код-ревью для AI-ассистентов: **Claude (Code и Claude.ai), ChatGPT (Custom GPT и Projects), Codex, Cursor, GitHub Copilot, Gemini, Windsurf, Cline и любых других ассистентов**. Превращает AI-ревью из размытых советов в **структурированный, последовательный и экспертный** процесс.

Покрывает **20+ языков и фреймворков**: более **21 000 строк** выверенных руководств по ревью - загружаются постепенно, экономя контекстное окно.

---

### &#10024; Ключевые возможности

- **Кроссплатформенность** - один навык для любого агента: готовые инструкции для ChatGPT и Claude.ai Projects (включая русские версии), нативная установка для Claude Code и штатные файлы входа для Codex, Cursor, Copilot, Gemini CLI, Windsurf и Cline. Самодостаточный [универсальный промпт](adapters/universal-prompt.md) закрывает ассистентов без доступа к файлам. См. [adapters/README.md](adapters/README.md).
- **Прогрессивная загрузка** - ядро ~310 строк; языковые руководства (200–1100 строк каждое) загружаются только при необходимости.
- **OWASP-аудит безопасности** - полная процедура по OWASP Top 10:2025, API Security Top 10:2023 и LLM Top 10:2025. У каждой находки есть категория OWASP и CWE, в конце - отчёт о покрытии по категориям. Опирается на `scripts/security-scan.py`: сканер без зависимостей, 70+ правил с привязкой к OWASP/CWE для 10 языков.
- **Безопасное исправление** - [план исправлений](reference/remediation-playbook.md): по одной подтверждённой находке за раз. Против типичных сбоев моделей при правках: пакетных изменений, «размывания» контекста, подгонки тестов и бесконечных повторов.
- **Экономия токенов** - сначала сканер, затем чтение только указанного кода, по одному руководству за раз, повторяющиеся находки группируются.
- **Самопроверка** - `python scripts/validate_skill.py` проверяет структуру, целостность ссылок, файлы входа для всех платформ, лимиты символов адаптеров и запускает тесты скрипта.
- **Четырёхэтапный процесс** - от понимания контекста до чёткой обратной связи.
- **Метки серьёзности** - каждая находка классифицирована: `blocking` · `important` · `nit` · `suggestion` · `learning` · `praise`
- **Контракт вывода** - каждая находка содержит место, влияние и конкретное исправление; каждое ревью завершается вердиктом и списком реально выполненных проверок.
- **Проверка перед вердиктом** - запуск тестов/линтеров, когда среда позволяет; честный отчёт, если они не запускались.
- **Безопасность прежде всего** - отдельные чек-листы безопасности для каждой языковой экосистемы.
- **Ревью ИИ-кода** - отдельное руководство: галлюцинированные API, typosquatting/slopsquatting зависимостей, зеркалирование реализации в тестах.
- **Качество тестов** - тесты ревьюятся так же строго, как код: работоспособность, нестабильность, чрезмерные моки, покрытие против уверенности.
- **Совместный тон** - вопросы вместо приказов, предложения вместо директив.
- **Git-хуки** - [`review-hooks/`](review-hooks/README.md): хуки `commit-msg` и `pre-push` проверяют имена веток, сообщения коммитов и секреты обычным кодом (без ИИ), плюс необязательное изолированное ИИ-ревью (рекомендательное или обязательное). Проверено на Windows и Linux.
- **Разделение с автоматикой** - чёткая граница между тем, что ловит ревью, и тем, что обрабатывают линтеры.

---

### &#127760; Поддерживаемые языки и фреймворки

| Категория | Технология | Файл руководства | Строк |
|-----------|------------|------------------|-------|
| **Фронтенд** | React 19 / Next.js / TanStack Query v5 | `reference/react.md` | ~870 |
| | Vue 3.5 Composition API | `reference/vue.md` | ~920 |
| | Angular 17+ / Signals / Zoneless | `reference/angular.md` | ~770 |
| | Svelte 5 / SvelteKit | `reference/svelte.md` | ~1060 |
| | CSS / Less / Sass | `reference/css-less-sass.md` | ~660 |
| | TypeScript | `reference/typescript.md` | ~1020 |
| **Бэкенд** | Java 17/21 + Spring Boot 3 | `reference/java.md` | ~410 |
| | Java 8 + Spring Boot 2 | `reference/java8.md` | ~580 |
| | FastAPI | `reference/fastapi.md` | ~590 |
| | PHP 8.x | `reference/php.md` | ~700 |
| | Ruby 3.4+/4.0 + Rails 8.x | `reference/ruby.md` | ~960 |
| | NestJS | `reference/nestjs.md` | ~590 |
| | Django / DRF | `reference/django.md` | ~1030 |
| | Python | `reference/python.md` | ~1070 |
| | Go | `reference/go.md` | ~990 |
| | Rust | `reference/rust.md` | ~840 |
| | C# / .NET 8 | `reference/csharp.md` | ~520 |
| **Мобильные / системные** | Kotlin / Android | `reference/kotlin.md` | ~1020 |
| | Swift / SwiftUI | `reference/swift.md` | ~930 |
| | Dart / Flutter | `reference/dart.md` | ~670 |
| | C | `reference/c.md` | ~890 |
| | C++ | `reference/cpp.md` | ~890 |
| | Zig | `reference/zig.md` | ~440 |
| | Qt | `reference/qt.md` | ~760 |
| **Сквозные темы** | Ревью архитектуры | `reference/architecture-review-guide.md` | ~470 |
| | Ревью производительности | `reference/performance-review-guide.md` | ~820 |
| | Универсальные антипаттерны | `reference/code-quality-universal.md` | ~490 |
| | Ревью безопасности | `reference/security-review-guide.md` | ~510 |
| | OWASP-аудит (Top 10:2025, API, LLM) | `reference/owasp-security-audit.md` | ~250 |
| | План исправлений находок | `reference/remediation-playbook.md` | ~130 |
| | Качество тестов | `reference/test-quality-review.md` | ~220 |
| | Ревью ИИ-кода | `reference/ai-generated-code-review.md` | ~260 |
| | N+1 запросы | `reference/cross-cutting/n-plus-one-queries.md` | ~310 |
| | Принципы обработки ошибок | `reference/cross-cutting/error-handling-principles.md` | ~490 |
| | Async и конкурентность | `reference/cross-cutting/async-concurrency-patterns.md` | ~540 |
| | Защита от SQL-инъекций | `reference/cross-cutting/sql-injection-prevention.md` | ~310 |
| | Защита от XSS | `reference/cross-cutting/xss-prevention.md` | ~260 |

Полная структура репозитория приведена в [английском разделе](#english).

---

### &#128260; Четырёхэтапный процесс ревью

```
Этап 1 - Сбор контекста
  Понять объём PR, связанные задачи и замысел
                    |
                    v
Этап 2 - Ревью высокого уровня
  Архитектура - влияние на производительность - стратегия тестирования
                    |
                    v
Этап 3 - Построчный анализ
  Логика - безопасность - поддерживаемость - граничные случаи
                    |
                    v
Этап 4 - Проверка, итоги и решение
  Тесты/линтеры - структурированная обратная связь - вердикт - пункты действий
```

---

### &#127991;&#65039; Метки серьёзности

| Метка | Значение |
|-------|----------|
| &#128308; `blocking` | Исправить до merge |
| &#128993; `important` | Следует исправить; обсудите, если не согласны |
| &#128994; `nit` | Мелочь стиля или предпочтений; не блокирует |
| &#128161; `suggestion` | Необязательное улучшение, стоит рассмотреть |
| &#128218; `learning` | Образовательная заметка для автора |
| &#127881; `praise` | Явно отметить отличную работу |

Merge блокирует только 🔴 `blocking`. 🔴 / 🟡 / 🟢 - три уровня серьёзности; остальные метки - неблокирующие пометки. Метки остаются на английском при любом языке ответа, чтобы их могли разбирать инструменты.

---

### &#128640; Установка

Полные инструкции по платформам: [adapters/README.md](adapters/README.md).

**Claude Code** - скопируйте папку в каталог skills:

```bash
# macOS / Linux
cp -r code-review-skill-main ~/.claude/skills/code-review-skill

# Windows (PowerShell)
Copy-Item -Recurse code-review-skill-main "$env:USERPROFILE\.claude\skills\code-review-skill"
```

**Claude.ai (Projects)** - вставьте [adapters/claude-project-instructions.ru.md](adapters/claude-project-instructions.ru.md) в пользовательские инструкции проекта, затем загрузите `SKILL.md` и нужные руководства `reference/` как знания проекта.

**ChatGPT (Custom GPT или Project)** - вставьте [adapters/chatgpt-instructions.ru.md](adapters/chatgpt-instructions.ru.md) в поле Instructions (укладывается в лимит 8000 символов), затем загрузите `SKILL.md` и соответствующие `reference/*.md` как Knowledge / источники проекта.

**Codex, Cursor, Copilot, Windsurf, Cline, Gemini CLI** - оставьте папку в рабочем пространстве; для каждой платформы уже есть свой файл входа (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursorrules`, `.cursor/rules/`, `.github/copilot-instructions.md`, `.windsurfrules`, `.clinerules`), и все они направляют агента к `SKILL.md`.

**Любой другой ассистент (Gemini, Grok, DeepSeek, Qwen, Mistral, локальные модели)** - вставьте [adapters/universal-prompt.ru.md](adapters/universal-prompt.ru.md) (английская версия: [universal-prompt.md](adapters/universal-prompt.md)) как системный промпт или первое сообщение: он самодостаточен и не требует загрузки файлов.

**Любой чат-ассистент** - вставьте универсальный промпт выше либо `SKILL.md` и руководства для вашего языка, затем вставьте diff.

Проверить корректность установки:

```bash
python scripts/validate_skill.py
```

---

### &#128161; Использование

После настройки просто попросите ревью:

```
Используй code-review-skill, чтобы сделать ревью этого PR
```

В ChatGPT / Claude.ai вставьте diff или файл и напишите «Сделай ревью этого изменения» - настроенные инструкции запускают тот же четырёхэтапный процесс. Ревью выполняется на языке запроса.

**Примеры запросов:**

| Запрос | Что происходит |
|--------|----------------|
| `Сделай ревью этого React-компонента` | Загружается `react.md` - Hooks, Server Components, Suspense |
| `Ревью этого Java PR` | Загружается `java.md` - виртуальные потоки, JPA, Spring Boot 3 |
| `Ревью безопасности этого Go-сервиса` | Загружаются `go.md` + `security-review-guide.md` |
| `Ревью архитектуры` | Загружается `architecture-review-guide.md` - SOLID, антипаттерны, связность |
| `Ревью производительности` | Загружается `performance-review-guide.md` - Web Vitals, N+1, сложность |
| `OWASP-аудит безопасности репозитория` | Запускается `security-scan.py`, загружается `owasp-security-audit.md` - покрытие A01–A10, OWASP + CWE у каждой находки |
| `Исправь находки из аудита` | Загружается `remediation-playbook.md` - по одной находке, каждая подтверждена проверкой, которая сначала падала, а потом проходит |
| `Проверь качество тестов в этом PR` | Загружается `test-quality-review.md` - утверждения, моки, нестабильность |
| `Ревью ИИ-сгенерированного кода` | Загружается `ai-generated-code-review.md` - API, зависимости, зеркалирование тестов |

---

### &#129309; Участие в разработке

Вклад приветствуется! Правила - в [CONTRIBUTING.md](./CONTRIBUTING.md).

**Идеи:**
- Новые языковые руководства (Elixir, Scala, Lua...)
- Руководства по фреймворкам (Laravel, Spring WebFlux...)
- Дополнительные чек-листы и шаблоны
- Переводы основной документации

---

### &#128196; Лицензия

MIT - см. [LICENSE](./LICENSE) · Author/Coder: Kaskobian

---

<div align="center">
  Made with &#10084;&#65039; for developers who care about code quality
</div>
