// review-hooks/lib/git.mjs - small synchronous git helpers.
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { spawnSync } from "node:child_process";
import { mergeConfig } from "./rules.mjs";

export const ZERO = /^0+$/;

export function git(args, opts = {}) {
  const r = spawnSync("git", args, {
    encoding: "utf8", maxBuffer: 512 * 1024 * 1024, windowsHide: true, ...opts,
  });
  if (r.error || r.status !== 0)
    throw new Error(`git ${args[0]}: ${(r.error?.message || r.stderr || "").trim()}`);
  return r.stdout.replace(/\s+$/, "");
}
export const tryGit = (args, opts) => { try { return git(args, opts); } catch { return null; } };

export const repoRoot = () => git(["rev-parse", "--show-toplevel"]);
export const gitDir = () => git(["rev-parse", "--absolute-git-dir"]);
export const currentBranch = () => tryGit(["symbolic-ref", "--quiet", "--short", "HEAD"]);

export function loadConfig(root = repoRoot()) {
  const file = path.join(root, ".review-hooks.json");
  let user = {};
  if (fs.existsSync(file)) {
    try { user = JSON.parse(fs.readFileSync(file, "utf8")); }
    catch (e) { throw new Error(`.review-hooks.json is not valid JSON: ${e.message}`); }
  }
  const cfg = mergeConfig(user);
  cfg.baseBranch = process.env.REVIEW_HOOKS_BASE || cfg.baseBranch;
  return cfg;
}

/** Stable, filesystem-safe key for a branch name. */
export function branchKey(branch) {
  return branch.replace(/[^a-zA-Z0-9._-]/g, "_").slice(0, 60) + "-" +
    crypto.createHash("sha256").update(branch).digest("hex").slice(0, 8);
}

export function stateDir() {
  const dir = path.join(gitDir(), "review-hooks");
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

export function readReviewState(branch) {
  try { return JSON.parse(fs.readFileSync(path.join(stateDir(), branchKey(branch) + ".json"), "utf8")); }
  catch { return null; }
}

/**
 * Is the stored AI review for `branch` about exactly this code?
 * The review covers merge-base(base, head)..head, so both ends must match.
 */
export function reviewFreshness(branch, headSha, baseRef) {
  const state = readReviewState(branch);
  if (!state) return { fresh: false, state, why: "no AI review has been run for this branch" };
  if (state.status !== "done")
    return { fresh: false, state, why: `last AI review ${state.status}${state.reason ? ": " + state.reason : ""}` };
  const base = tryGit(["merge-base", baseRef, headSha]);
  if (state.head !== headSha) return { fresh: false, state, why: `code changed since the review (${state.head.slice(0, 8)} -> ${headSha.slice(0, 8)})` };
  if (base && state.base !== base) return { fresh: false, state, why: "the base moved since the review (rebased or merged)" };
  return { fresh: true, state };
}
