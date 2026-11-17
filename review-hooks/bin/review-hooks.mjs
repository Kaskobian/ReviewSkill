#!/usr/bin/env node
// review-hooks/bin/review-hooks.mjs - Node.js 20+, no dependencies.
//
//   review-hooks check            branch name, commit messages, secrets, vulnerable deps, AI review status
//   review-hooks deps             known-vulnerable dependencies only (--verbose, --json)
//   review-hooks review           run the (optional) AI review of this branch now
//   review-hooks status           show the last AI review for this branch
//   review-hooks msg <file>       check one commit message (used by commit-msg)
//   review-hooks pre-push         used by the pre-push hook (reads refs on stdin)
//   review-hooks install | uninstall
//
// Add --json to check/status/deps for machine-readable output; --no-deps skips the
// network dependency check (also REVIEW_HOOKS_NO_DEPS=1, e.g. for one push).
// Exit codes: 0 ok, 1 a check failed, 2 usage or setup error.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { git, tryGit, ZERO, repoRoot, currentBranch, loadConfig, readReviewState, reviewFreshness } from "../lib/git.mjs";
import { checkBranchName, checkCommitMessage, cleanMessage } from "../lib/rules.mjs";
import { scanDiffForSecrets, describeSecretHits } from "../lib/secrets.mjs";
import { runReview } from "../lib/review.mjs";
import { checkDependencies, summarize, formatReport, defaultCacheDir } from "../lib/deps/check.mjs";
import { isDependencyFile } from "../lib/deps/lockfiles.mjs";

const kitDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const color = process.stdout.isTTY && !process.env.NO_COLOR;
const paint = (c, s) => color ? `\x1b[${c}m${s}\x1b[0m` : s;
const TAG = { pass: paint(32, "PASS"), fail: paint(31, "FAIL"), warn: paint(33, "WARN"), info: paint(36, "INFO") };

// ── checks over a commit range ─────────────────────────────────────────────

function commitsIn(range) {
  const out = tryGit(["log", "--no-merges", "--format=%H%x1f%B%x1e", range]) || "";
  return out.split("\x1e").map(s => s.trim()).filter(Boolean)
    .map(s => { const [sha, ...msg] = s.split("\x1f"); return { sha, message: msg.join("\x1f") }; });
}

const depsEnabled = (cfg, argv = []) =>
  cfg.dependencies?.enabled !== false && !argv.includes("--no-deps") && process.env.REVIEW_HOOKS_NO_DEPS !== "1";

/** Did any dependency file change between two commits? */
function depFilesChanged(from, to) {
  const out = tryGit(["diff", "--name-only", "-z", from || "4b825dc642cb6eb9a060e54bf8d69288fbee4904", to]) || "";
  return out.split("\0").some(f => f && isDependencyFile(f));
}

async function depsResult(cfg, base, head) {
  const report = await checkDependencies({
    head, base, policy: cfg.dependencies,
    cacheDir: defaultCacheDir(git(["rev-parse", "--absolute-git-dir"])),
    apiKey: process.env.NVD_API_KEY,
  });
  return {
    status: report.status, name: "No known-vulnerable dependencies introduced", detail: summarize(report),
    fix: report.status === "pass" ? undefined
      : report.status === "fail" ? "upgrade to the version shown; details: review-hooks deps"
      : "details: review-hooks deps",
  };
}

async function rangeChecks({ cfg, branch, from, to, aiGate, allowAutosquash, deps = true, depsOnlyIfChanged = false }) {
  const results = [];
  const add = (status, name, detail, fix) => results.push({ status, name, detail, fix });

  if (branch !== undefined) {
    const b = checkBranchName(branch, cfg);
    add(b.ok ? "pass" : "fail", "Branch name", b.why, b.ok ? undefined : `git branch -m ${cfg.branchExample || "<new-name>"}`);
  }
  const range = from ? `${from}..${to}` : to;
  const commits = commitsIn(range);
  const bad = commits
    .map(c => ({ ...c, r: checkCommitMessage(c.message, cfg, { allowAutosquash }) }))
    .filter(c => !c.r.ok);
  add(bad.length ? "fail" : "pass", "Commit messages",
    bad.length
      ? bad.slice(0, 5).map(c => `${c.sha.slice(0, 8)} "${cleanMessage(c.message)[0] || ""}": ${c.r.errors[0]}`).join("; ") +
        (bad.length > 5 ? `; +${bad.length - 5} more` : "")
      : `${commits.length} commit(s) checked`,
    bad.length ? "git rebase -i " + (from ? from.slice(0, 12) : cfg.baseBranch) + "  (reword the listed commits)" : undefined);

  if (cfg.secrets !== false) {
    // Scan every commit, not only the net diff: a secret added and then
    // deleted is still in history and still leaks on push.
    const patch = tryGit(["log", "-p", "--no-merges", "--no-ext-diff", "--no-textconv", "--format=", range]) || "";
    const hits = scanDiffForSecrets(patch, { allow: cfg.secretsAllow });
    add(hits.length ? "fail" : "pass", "No secrets in commits", hits.length ? describeSecretHits(hits) : undefined,
      hits.length ? "remove them from history (git rebase -i), rotate them if real, or add fixture paths to secretsAllow" : undefined);
  }

  // Known-vulnerable dependency versions (OSV.dev + CISA KEV + optional NVD).
  // Only versions this range introduces can fail. On push, skip the network
  // entirely when no dependency file changed: nothing new can be introduced.
  if (deps && !(depsOnlyIfChanged && !depFilesChanged(from, to))) {
    try { results.push(await depsResult(cfg, from, to)); }
    catch (e) {
      add("warn", "No known-vulnerable dependencies introduced", "not checked: " + String(e.message || e).split("\n")[0], "review-hooks deps");
    }
  }

  if (cfg.aiReview !== "off" && branch) {
    const f = reviewFreshness(branch, to, cfg.baseBranch);
    const status = f.fresh ? "pass" : (cfg.aiReview === "required" && aiGate ? "fail" : "warn");
    add(status, `AI review (${cfg.aiReview})`,
      f.fresh ? `${f.state.verdict || "no verdict"}, report: ${path.relative(process.cwd(), f.state.report)}` : f.why,
      f.fresh ? undefined : "review-hooks review");
  }
  return results;
}

function print(title, results) {
  console.log(title);
  for (const r of results) {
    console.log(`  ${TAG[r.status]}  ${r.name}${r.detail ? ": " + r.detail : ""}`);
    if (r.fix && r.status !== "pass") console.log(`        -> ${r.fix}`);
  }
}

// ── commands ───────────────────────────────────────────────────────────────

async function cmdCheck(cfg, json, argv) {
  const branch = currentBranch();
  const head = git(["rev-parse", "HEAD"]);
  const baseOk = tryGit(["rev-parse", "--verify", "--quiet", cfg.baseBranch + "^{commit}"]);
  const base = baseOk && tryGit(["merge-base", cfg.baseBranch, head]);
  const results = await rangeChecks({ cfg, branch, from: base, to: head, aiGate: true, allowAutosquash: false, deps: depsEnabled(cfg, argv) });
  if (!baseOk) results.unshift({ status: "warn", name: "Base branch", detail: `${cfg.baseBranch} not found, checked all history`, fix: "git fetch" });
  if (json) console.log(JSON.stringify({ branch, base: cfg.baseBranch, results }, null, 2));
  else print(`review-hooks check: ${branch || "(detached)"} vs ${cfg.baseBranch}`, results);
  return results.some(r => r.status === "fail") ? 1 : 0;
}

async function cmdDeps(cfg, argv) {
  const head = git(["rev-parse", "HEAD"]);
  const baseOk = tryGit(["rev-parse", "--verify", "--quiet", cfg.baseBranch + "^{commit}"]);
  const base = baseOk ? tryGit(["merge-base", cfg.baseBranch, head]) : null;
  const report = await checkDependencies({
    head, base, policy: cfg.dependencies,
    cacheDir: defaultCacheDir(git(["rev-parse", "--absolute-git-dir"])), apiKey: process.env.NVD_API_KEY,
  });
  if (argv.includes("--json")) console.log(JSON.stringify(report, null, 2));
  else {
    console.log(`review-hooks deps: ${currentBranch() || "(detached)"} vs ${base ? cfg.baseBranch : "(base not found: everything counts as introduced)"}\n`);
    console.log(formatReport(report, { verbose: argv.includes("--verbose") }));
    console.log(`\nResult: ${report.status.toUpperCase()}`);
  }
  return report.status === "fail" ? 1 : 0;
}

async function cmdReview(cfg) {
  const s = await runReview({ cfg, kitDir, log: m => console.log(m) });
  const tag = { done: "pass", skipped: "warn", blocked: "fail", failed: "fail" }[s.status] || "info";
  console.log(`${TAG[tag]}  AI review ${s.status}${s.reason ? ": " + s.reason : ""}`);
  if (s.report) console.log(`        report: ${s.report}${s.verdict ? `  (verdict: ${s.verdict})` : ""}`);
  return s.status === "done" || s.status === "skipped" ? 0 : 1;
}

function cmdStatus(cfg, json) {
  const branch = currentBranch();
  const s = branch && readReviewState(branch);
  if (json) { console.log(JSON.stringify(s || null, null, 2)); return 0; }
  if (!s) { console.log("No AI review recorded for this branch. Run: review-hooks review"); return 0; }
  const f = reviewFreshness(branch, git(["rev-parse", "HEAD"]), cfg.baseBranch);
  console.log(`${s.status}${s.reason ? ": " + s.reason : ""}${s.verdict ? ` (verdict: ${s.verdict})` : ""}`);
  console.log(f.fresh ? "Up to date with the current code." : `Out of date: ${f.why}`);
  if (s.report) console.log(`Report: ${s.report}`);
  return 0;
}

function cmdMsg(cfg, file) {
  if (!file) { console.error("usage: review-hooks msg <file>"); return 2; }
  const r = checkCommitMessage(fs.readFileSync(file, "utf8"), cfg, { allowAutosquash: true });
  if (r.ok) return 0;
  console.error("review-hooks: commit message rejected");
  for (const e of r.errors) console.error("  - " + e);
  if (cfg.commitStyle === "conventional" || cfg.commitStyle === undefined)
    console.error("  example: feat(api): add CSV export to reports");
  console.error("  (bypass once with git commit --no-verify)");
  return 1;
}

function readStdin() { try { return fs.readFileSync(0, "utf8"); } catch { return ""; } }

async function cmdPrePush(cfg) {
  // stdin: "<local ref> <local sha> <remote ref> <remote sha>" per line
  let rc = 0;
  for (const line of readStdin().split("\n").map(l => l.trim()).filter(Boolean)) {
    const [localRef, localSha, remoteRef, remoteSha] = line.split(/\s+/);
    if (ZERO.test(localSha)) continue;                              // deleting a remote branch
    if (!localRef.startsWith("refs/heads/")) continue;              // tags
    const branch = localRef.slice("refs/heads/".length);
    let from = ZERO.test(remoteSha) ? null : remoteSha;
    if (from && !tryGit(["cat-file", "-e", from + "^{commit}"])) from = null; // remote has commits we lack
    if (!from) {
      const baseOk = tryGit(["rev-parse", "--verify", "--quiet", cfg.baseBranch + "^{commit}"]);
      from = baseOk ? tryGit(["merge-base", cfg.baseBranch, localSha]) : null;
    }
    const isShared = (cfg.allowBranches || []).includes(branch);
    const results = await rangeChecks({
      cfg, branch: isShared ? undefined : branch, from, to: localSha,
      aiGate: !isShared, allowAutosquash: false, deps: depsEnabled(cfg), depsOnlyIfChanged: true,
    });
    print(`review-hooks pre-push: ${branch} -> ${remoteRef.replace(/^refs\/heads\//, "")}`, results);
    if (results.some(r => r.status === "fail")) rc = 1;
  }
  if (rc) console.error("\nPush blocked. Fix the items above, or bypass once with git push --no-verify.");
  return rc;
}

function cmdInstall(uninstall) {
  const root = repoRoot();
  const hooks = path.relative(root, path.join(kitDir, "hooks")).split(path.sep).join("/");
  if (hooks.startsWith("..")) {
    console.error(`review-hooks must live inside the repository (found it at ${kitDir}).`);
    return 2;
  }
  const current = tryGit(["config", "--local", "--get", "core.hooksPath"]);
  if (uninstall) {
    if (current === hooks) git(["config", "--local", "--unset", "core.hooksPath"]);
    console.log(current === hooks ? "Removed core.hooksPath." : "core.hooksPath was not set by review-hooks; left unchanged.");
    return 0;
  }
  if (current && current !== hooks) {
    console.error(`core.hooksPath is already "${current}". Merge those hooks into ${hooks}/ first, or unset it.`);
    return 2;
  }
  const legacy = path.join(git(["rev-parse", "--git-path", "hooks"]));
  const existing = fs.existsSync(legacy)
    ? fs.readdirSync(legacy).filter(f => !f.endsWith(".sample")) : [];
  git(["config", "--local", "core.hooksPath", hooks]);
  for (const h of ["commit-msg", "pre-push"]) {
    try { fs.chmodSync(path.join(kitDir, "hooks", h), 0o755); } catch { /* Windows */ }
  }
  console.log(`Installed: core.hooksPath = ${hooks}`);
  if (existing.length) console.log(`Note: ${existing.join(", ")} in .git/hooks no longer run. Move them into ${hooks}/ if needed.`);
  const cfg = loadConfig(root);
  if (!tryGit(["rev-parse", "--verify", "--quiet", cfg.baseBranch + "^{commit}"]))
    console.log(`Note: base branch ${cfg.baseBranch} not found. Run git fetch, or set baseBranch in .review-hooks.json.`);
  return 0;
}

const HELP = fs.readFileSync(fileURLToPath(import.meta.url), "utf8").split("\n")
  .slice(2, 14).map(l => l.replace(/^\/\/ ?/, "")).join("\n");

async function main(argv) {
  const [cmd, ...rest] = argv;
  const json = rest.includes("--json");
  if (!cmd || cmd === "-h" || cmd === "--help" || cmd === "help") { console.log(HELP); return 0; }
  if (cmd === "install" || cmd === "uninstall") return cmdInstall(cmd === "uninstall");
  const cfg = loadConfig();
  switch (cmd) {
    case "check": return cmdCheck(cfg, json, rest);
    case "deps": return cmdDeps(cfg, rest);
    case "review": return cmdReview(cfg);
    case "status": return cmdStatus(cfg, json);
    case "msg": return cmdMsg(cfg, rest[0]);
    case "pre-push": return cmdPrePush(cfg);
    default: console.error(`unknown command "${cmd}"\n\n${HELP}`); return 2;
  }
}

main(process.argv.slice(2)).then(
  code => { process.exitCode = code; },
  e => { console.error("review-hooks: " + (e.message || e)); process.exitCode = 2; });
