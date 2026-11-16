# review-hooks

Git hooks that enforce team rules with plain code, plus an **optional** AI
review that you run when you want it.

- **Deterministic first.** Branch names, commit messages and secret
  detection are checked by regular expressions with exit codes. Nothing is
  sent to an AI to decide whether a commit or push is allowed.
- **AI is opt-in.** `aiReview` is `off` by default. Turn it on as `advisory`
  (shows a warning) or `required` (blocks the push until a review matches
  the exact code being pushed).
- **No dependencies.** Node.js 20+ and Git. Works on Linux, macOS and
  Windows (Git Bash).

| Hook | Runs | Checks |
|---|---|---|
| `commit-msg` | every commit | message format |
| `pre-push` | every push | branch name, every pushed commit's message, secrets in every pushed commit, AI review status |

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
```

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
  "maxDiffBytes": 500000
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
node --test review-hooks/tests/                    # unit + end-to-end (real git, fake agent)
bash review-hooks/tests/probe-claude-isolation.sh  # needs the real claude CLI
```
