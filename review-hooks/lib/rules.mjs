// review-hooks/lib/rules.mjs - pure, deterministic rule checks (no git, no AI).

export const DEFAULTS = Object.freeze({
  baseBranch: "origin/main",
  branchPattern: "^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)/[a-z0-9][a-z0-9._-]*$",
  branchExample: "feat/export-csv",
  allowBranches: ["main", "master", "develop"],
  commitStyle: "conventional",       // "conventional" | "none" | { pattern, example }
  maxSubjectLength: 72,
  requireBody: false,
  secrets: true,
  secretsAllow: [],                  // globs skipped by the secret scan, e.g. "tests/fixtures/**"
  aiReview: "off",                   // "off" | "advisory" | "required"
  agent: "claude",                   // "claude" | { command, args }
  agentTimeoutSeconds: 900,
  maxDiffBytes: 500000,
});

const CONVENTIONAL = /^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9._\/-]+\))?!?: \S/;
const GIT_GENERATED = /^(Merge (branch|pull request|remote-tracking branch|tag) |Merge [0-9a-f]{7,} |Revert ")/;
const AUTOSQUASH = /^(fixup|squash|amend)! /;

export function checkBranchName(branch, cfg = DEFAULTS) {
  if (!branch) return { ok: false, why: "HEAD is detached (not on a branch)" };
  if ((cfg.allowBranches || []).includes(branch)) return { ok: true };
  if (!cfg.branchPattern) return { ok: true };
  if (new RegExp(cfg.branchPattern).test(branch)) return { ok: true };
  return {
    ok: false,
    why: `"${branch}" does not match ${cfg.branchPattern}` +
      (cfg.branchExample ? ` (example: ${cfg.branchExample})` : ""),
  };
}

/** Strip comment lines and trailing blank lines the way `git commit` does. */
export function cleanMessage(message) {
  let lines = message.replace(/\r\n/g, "\n").split("\n");
  // Everything below a scissors line is diff text from `commit -v`.
  const cut = lines.findIndex(l => /^# -+ >8 -+$/.test(l));
  if (cut !== -1) lines = lines.slice(0, cut);
  lines = lines.filter(l => !l.startsWith("#")).map(l => l.replace(/\s+$/, ""));
  while (lines.length && lines[lines.length - 1] === "") lines.pop();
  while (lines.length && lines[0] === "") lines.shift();
  return lines;
}

/**
 * @param {string} message
 * @param {object} cfg
 * @param {{ allowAutosquash?: boolean }} [opts] fixup!/squash! commits are fine
 *        locally but should not be pushed to shared branches.
 */
export function checkCommitMessage(message, cfg = DEFAULTS, opts = { allowAutosquash: true }) {
  const lines = cleanMessage(message);
  const subject = lines[0] || "";
  const errors = [];
  if (!subject) return { ok: false, errors: ["empty commit message"] };
  if (GIT_GENERATED.test(subject)) return { ok: true, errors: [] };
  if (AUTOSQUASH.test(subject)) {
    return opts.allowAutosquash
      ? { ok: true, errors: [] }
      : { ok: false, errors: [`"${subject}" is an autosquash commit: run git rebase -i --autosquash before pushing`] };
  }

  const style = cfg.commitStyle ?? "conventional";
  if (style === "conventional") {
    if (!CONVENTIONAL.test(subject)) {
      errors.push(`subject "${subject}" is not Conventional Commits: type(scope): description`);
      if (/^[A-Z][a-z]+(\(.+\))?: /.test(subject)) errors.push("the type must be lowercase (feat, fix, docs, ...)");
      else if (/^(feature|bugfix|bug|hotfix)\b/i.test(subject)) errors.push('use "feat" or "fix" as the type');
    }
  } else if (style && typeof style === "object" && style.pattern) {
    if (!new RegExp(style.pattern).test(subject))
      errors.push(`subject "${subject}" does not match ${style.pattern}` + (style.example ? ` (example: ${style.example})` : ""));
  }

  const max = cfg.maxSubjectLength ?? 72;
  if (max && subject.length > max) errors.push(`subject is ${subject.length} characters (max ${max})`);
  if (lines.length > 1 && lines[1] !== "") errors.push("add a blank line between the subject and the body");
  if (cfg.requireBody && !lines.slice(1).join("").trim())
    errors.push("a body is required: explain what changes and why");
  return { ok: errors.length === 0, errors };
}

export function mergeConfig(user = {}) {
  const cfg = { ...DEFAULTS, ...user };
  if (!["off", "advisory", "required"].includes(cfg.aiReview))
    throw new Error(`aiReview must be "off", "advisory" or "required", got ${JSON.stringify(cfg.aiReview)}`);
  if (cfg.branchPattern) new RegExp(cfg.branchPattern); // throws on a bad pattern
  return cfg;
}
