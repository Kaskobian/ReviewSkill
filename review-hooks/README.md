# review-hooks

Git hooks that enforce team rules with plain code, plus an **optional** AI
review that you run when you want it.

- **Deterministic first.** Branch names, commit messages, secrets and
  known-vulnerable dependency versions are checked by plain code with exit codes. Nothing is
  sent to an AI to decide whether a commit or push is allowed.
- **AI is opt-in.** `aiReview` is `off` by default. Turn it on as `advisory`
  (shows a warning) or `required` (blocks the push until a review matches
  the exact code being pushed).
- **No dependencies.** Node.js 20+ and Git. Works on Linux, macOS and
  Windows (Git Bash).

| Hook | Runs | Checks |
|---|---|---|
| `commit-msg` | every commit | message format |
| `pre-push` | every push | branch name, every pushed commit's message, secrets in every pushed commit, vulnerable dependencies (only when a lock file changed), AI review status |

## Install

Copy the `review-hooks/` folder into your repository, commit it, then each
developer runs once per clone:

```bash
node review-hooks/bin/review-hooks.mjs install
```

This sets `core.hooksPath` to `review-hooks/hooks`. It refuses to overwrite
an existing `core.hooksPath` (Husky, lefthook, and so on).
`node review-hooks/bin/review-hooks.mjs uninstall` removes it.

## Commands

```bash
node review-hooks/bin/review-hooks.mjs check    # everything, for the current branch (add --json for CI)
node review-hooks/bin/review-hooks.mjs review   # run the AI review now
node review-hooks/bin/review-hooks.mjs status   # last AI review and whether it is still current
node review-hooks/bin/review-hooks.mjs deps     # known-vulnerable dependencies (--verbose, --json)
```

`--no-deps` (or `REVIEW_HOOKS_NO_DEPS=1`) skips the network dependency check.

Bypass a hook once with `git commit --no-verify` or `git push --no-verify`.
Hooks are a convenience, not a security boundary: run `check --json` in CI
for enforcement.

## Configuration

Optional `.review-hooks.json` at the repository root. Defaults shown:

```json
{
  "baseBranch": "origin/main",
  "branchPattern": "^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)/[a-z0-9][a-z0-9._-]*$",
  "branchExample": "feat/export-csv",
  "allowBranches": ["main", "master", "develop"],
  "commitStyle": "conventional",
  "maxSubjectLength": 72,
  "requireBody": false,
  "secrets": true,
  "secretsAllow": [],
  "aiReview": "off",
  "agent": "claude",
  "agentTimeoutSeconds": 900,
  "maxDiffBytes": 500000,
  "dependencies": {
    "enabled": true,
    "failOn": "critical",
    "failOnKev": true,
    "warnOn": "medium",
    "offline": "warn",
    "nvd": "gaps",
    "nvdMaxLookups": 10,
    "ignore": []
  }
}
```

- `commitStyle`: `"conventional"`, `"none"`, or your own rule:
  `{ "pattern": "^[A-Z]+-\\d+ ", "example": "PROJ-12 Add login" }`.
- `secretsAllow`: path globs skipped by the secret scan, e.g. `"tests/fixtures/**"`.
- `agent`: `"claude"` (Claude Code, run in isolated read-only mode) or any
  command that reads a prompt on stdin and prints Markdown, e.g.
  `{ "name": "codex", "command": "codex", "args": ["exec", "-"] }`.
- `skillFile`: optional path to a review method to include in the prompt.
  Defaults to the `SKILL.md` next to this folder, if present.
- `REVIEW_HOOKS_BASE` environment variable overrides `baseBranch`.

## Dependency check (no AI)

Reads the dependency files **committed** at the pushed commit and asks public
vulnerability databases about the exact versions:

| Source | Used for | Key |
|---|---|---|
| [OSV.dev](https://osv.dev) | Affected versions, the fixed version, CVSS vector | none |
| [CISA KEV](https://www.cisa.gov/known-exploited-vulnerabilities-catalog) | Is the CVE exploited in the wild | none |
| [NIST NVD](https://nvd.nist.gov) | CVSS score and CWE when OSV has none | optional `NVD_API_KEY` |

Files: `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`,
`packages.lock.json`, `*.csproj`/`*.fsproj`/`*.vbproj`,
`Directory.Packages.props`, `packages.config`, `requirements*.txt`,
`poetry.lock`, `uv.lock`, `Pipfile.lock`, `go.mod`, `Cargo.lock`,
`composer.lock`, `Gemfile.lock`, `gradle.lockfile`. Only exact versions;
ranges, variables and git/path dependencies are skipped, never guessed.

Policy:

- **Only what the branch introduces can fail.** A vulnerable version already
  on `baseBranch` is a warning, so nobody is blocked by inherited debt.
- An introduced package fails at `failOn` (default `critical`), or at any
  severity when the CVE is in CISA KEV (`failOnKev`).
- The suggested upgrade is the lowest version fixing every listed advisory,
  re-checked against OSV.
- OSV unreachable is a warning ("NOT checked"), never a silent pass;
  `"offline": "fail"` makes it blocking for CI.
- `pre-push` only calls the network when a dependency file changed in the
  pushed commits.
- Exceptions need a reason and an expiry date:
  `{ "id": "CVE-2021-23337", "package": "lodash", "reason": "template() not used with user input", "until": "2027-03-31" }`.

**NVD key.** Optional: by default NVD is asked only about CVEs OSV could not
score. Without a key lookups are spaced 6 s apart (NVD's public limit) and
capped per run. Get one at <https://nvd.nist.gov/developers/request-an-api-key>
and set `NVD_API_KEY` in your shell or CI secrets, never in the repository.
NVD terms say a key must not be shared, so for a team use one key in CI.

Results are cached in `.git/review-hooks/deps-cache/`. Mirrors: set
`REVIEW_HOOKS_OSV_URL`, `REVIEW_HOOKS_KEV_URL`, `REVIEW_HOOKS_NVD_URL`.

This product uses data from the NVD API but is not endorsed or certified by the NVD.

The same lookup for any repository, without hooks: `python scripts/dep-audit.py <path>`.

## How the AI review works

`review-hooks review`:

1. Finds the branch's commits since `merge-base(baseBranch, HEAD)`.
2. Scans the diff for secrets. On a match the status is `blocked`, and
   **nothing is sent to the agent**.
3. Skips diffs over `maxDiffBytes` instead of sending a huge prompt.
4. Checks out `HEAD` in a temporary detached worktree, with git hooks
   disabled, so the agent sees exactly the committed code, never your
   uncommitted edits.
5. Sends the diff on stdin. With Claude Code, the run is read-only (`Read`,
   `Grep`, `Glob`) and isolated from the repository's own `.claude/` settings,
   hooks and `.mcp.json` servers. Without that isolation, a branch could make
   `claude -p` run code on your machine. `tests/probe-claude-isolation.sh`
   demonstrates this against the real CLI.
6. Saves the report to `.git/review-hooks/<branch>.md`, tied to the head and
   base commits. A new commit or a rebase makes it out of date.

Every outcome is recorded with a reason: `done`, `skipped` (no agent, no
changes, too large, already running), `blocked` (secrets) or `failed`
(agent error, timeout, not logged in, base branch missing). The AI's verdict
is shown but never used to pass or fail anything. A person decides.

## Tests

```bash
node --test review-hooks/tests/                    # unit + end-to-end (real git, fake agent, fake OSV server)
bash review-hooks/tests/probe-claude-isolation.sh  # needs the real claude CLI
```
