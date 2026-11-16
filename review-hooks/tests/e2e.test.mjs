// review-hooks/tests/e2e.test.mjs - real git repos, fake agent, both hooks.
// Run: node --test review-hooks/tests/    (Windows: from Git Bash)
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const kit = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const CLI = path.join(kit, "bin", "review-hooks.mjs");
const FAKE = path.join(kit, "tests", "fake-agent.mjs");
const AWS = "AKIA" + "QWERTYUIOPASDFGH";

function sh(cwd, cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { cwd, encoding: "utf8", windowsHide: true, ...opts,
    env: { ...process.env, GIT_TERMINAL_PROMPT: "0", NO_COLOR: "1", ...opts.env } });
  return { code: r.status, out: (r.stdout || "") + (r.stderr || "") };
}

/** bare remote + clone with the kit copied in, committed and installed */
function makeRepo(t, config = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "rh-e2e-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const remote = path.join(dir, "remote.git"), work = path.join(dir, "work");
  sh(dir, "git", ["init", "-q", "--bare", "-b", "main", remote]);
  sh(dir, "git", ["clone", "-q", remote, work]);
  const g = (...a) => sh(work, "git", a);
  for (const [k, v] of [["user.name", "Test"], ["user.email", "t@example.com"], ["core.autocrlf", "false"], ["commit.gpgsign", "false"]])
    g("config", k, v);
  fs.cpSync(kit, path.join(work, "review-hooks"), {
    recursive: true, filter: s => !s.includes(`${path.sep}tests${path.sep}`) || s.endsWith("fake-agent.mjs"),
  });
  fs.writeFileSync(path.join(work, ".review-hooks.json"), JSON.stringify({
    agent: { name: "fake", command: process.execPath, args: [path.join(work, "review-hooks", "tests", "fake-agent.mjs")] },
    agentTimeoutSeconds: 20, ...config,
  }, null, 2));
  fs.writeFileSync(path.join(work, "app.js"), "console.log(1);\n");
  g("add", "-A"); g("commit", "-qm", "chore: initial commit"); g("push", "-q", "-u", "origin", "main");
  const inst = sh(work, process.execPath, [CLI.replace(kit, path.join(work, "review-hooks")), "install"]);
  assert.equal(inst.code, 0, inst.out);
  g("checkout", "-q", "-b", "feat/export");
  const cli = (args, env = {}) => sh(work, process.execPath, [path.join(work, "review-hooks", "bin", "review-hooks.mjs"), ...args], { env });
  const commit = (file, text, msg) => { fs.writeFileSync(path.join(work, file), text); g("add", "-A"); return g("commit", "-qm", msg); };
  const log = path.join(dir, "agent.log");
  const calls = () => fs.existsSync(log) ? fs.readFileSync(log, "utf8").trim().split("\n").map(JSON.parse) : [];
  return { dir, work, g, cli, commit, log, calls };
}

test("install sets core.hooksPath and refuses to clobber another one", t => {
  const r = makeRepo(t);
  assert.equal(r.g("config", "core.hooksPath").out.trim(), "review-hooks/hooks");
  r.g("config", "core.hooksPath", ".husky");
  const again = r.cli(["install"]);
  assert.equal(again.code, 2);
  assert.match(again.out, /already "\.husky"/);
  r.g("config", "core.hooksPath", "review-hooks/hooks");
  assert.equal(r.cli(["uninstall"]).code, 0);
  assert.equal(r.g("config", "--get", "core.hooksPath").code, 1);
});

test("commit-msg hook: rejects a bad message, accepts a good one", t => {
  const r = makeRepo(t);
  const bad = r.commit("a.js", "1\n", "fixed stuff");
  assert.notEqual(bad.code, 0);
  assert.match(bad.out, /Conventional Commits/);
  assert.equal(r.commit("a.js", "1\n", "feat: add export button").code, 0);
  assert.equal(r.g("commit", "-q", "--allow-empty", "--no-verify", "-m", "wip").code, 0, "--no-verify bypasses");
});

test("pre-push: blocks a secret even if a later commit deleted it", t => {
  const r = makeRepo(t);
  r.commit("cfg.js", `const k = "${AWS}";\n`, "feat: add config");
  r.commit("cfg.js", "const k = process.env.KEY;\n", "fix: read key from env");
  const push = r.g("push", "-q", "-u", "origin", "feat/export");
  assert.notEqual(push.code, 0, push.out);
  assert.match(push.out, /cfg\.js:1 \(aws-access-key\)/);
  assert.ok(!push.out.includes(AWS), "value never printed");
});

test("pre-push: bad branch name and bad message block; clean branch pushes", t => {
  const r = makeRepo(t);
  r.g("checkout", "-q", "-b", "Export-Stuff");
  r.g("commit", "-q", "--allow-empty", "--no-verify", "-m", "stuff");
  const p = r.g("push", "-q", "-u", "origin", "Export-Stuff");
  assert.notEqual(p.code, 0);
  assert.match(p.out, /Branch name/);
  assert.match(p.out, /"stuff"/);
  r.g("checkout", "-q", "feat/export");
  r.commit("b.js", "2\n", "feat: add b");
  const ok = r.g("push", "-q", "-u", "origin", "feat/export");
  assert.equal(ok.code, 0, ok.out);
  // Incremental push only checks new commits
  r.commit("c.js", "3\n", "feat: add c");
  assert.equal(r.g("push", "-q").code, 0);
});

test("pre-push: fixup! commits must be squashed before pushing", t => {
  const r = makeRepo(t);
  r.commit("b.js", "2\n", "feat: add b");
  r.commit("b.js", "3\n", "fixup! feat: add b");
  const p = r.g("push", "-q", "-u", "origin", "feat/export");
  assert.notEqual(p.code, 0);
  assert.match(p.out, /autosquash/);
});

test("pre-push: deleting a remote branch and pushing tags are not checked", t => {
  const r = makeRepo(t);
  r.commit("b.js", "2\n", "feat: add b");
  assert.equal(r.g("push", "-q", "-u", "origin", "feat/export").code, 0);
  assert.equal(r.g("push", "-q", "origin", "--delete", "feat/export").code, 0);
  r.g("tag", "v1"); assert.equal(r.g("push", "-q", "origin", "v1").code, 0);
});

test("review: happy path writes a report for HEAD from a clean checkout", t => {
  const r = makeRepo(t, { aiReview: "advisory" });
  r.commit("b.js", "2\n", "feat: add b");
  fs.writeFileSync(path.join(r.work, "UNCOMMITTED.txt"), "not committed");
  const out = r.cli(["review"], { FAKE_AGENT_LOG: r.log });
  assert.equal(out.code, 0, out.out);
  assert.match(out.out, /AI review done/);
  const [call] = r.calls();
  assert.equal(call.hasDiff, true);
  assert.equal(call.sawUncommitted, false, "agent ran in a clean worktree of HEAD");
  assert.ok(!fs.existsSync(call.cwd), "worktree removed afterwards");
  assert.match(r.cli(["status"]).out, /Up to date/);
  assert.equal(r.g("worktree", "list").out.trim().split("\n").length, 1);
});

test("review: secret blocks the review before the agent is called", t => {
  const r = makeRepo(t, { aiReview: "advisory" });
  r.commit("local.settings.json", "{}\n", "chore: add settings");
  const out = r.cli(["review"], { FAKE_AGENT_LOG: r.log });
  assert.equal(out.code, 1);
  assert.match(out.out, /blocked: possible secrets.*local\.settings\.json/);
  assert.equal(r.calls().length, 0);
});

test("review: every failure is visible with a reason", t => {
  const r = makeRepo(t, { aiReview: "advisory", agentTimeoutSeconds: 2 });
  r.commit("b.js", "2\n", "feat: add b");
  const cases = [
    ["fail", /failed: .*fake: model error/],
    ["notloggedin", /failed: .*Not logged in/],
    ["empty", /failed: .*exit code 0/],
    ["hang", /timed out after 2s/],
  ];
  for (const [mode, re] of cases) {
    const out = r.cli(["review"], { FAKE_AGENT_MODE: mode });
    assert.equal(out.code, 1, mode);
    assert.match(out.out, re, mode);
  }
  assert.equal(r.g("worktree", "list").out.trim().split("\n").length, 1, "no worktree left behind");
});

test("review: missing agent and missing base are skipped/failed, not silent", t => {
  const r = makeRepo(t, { aiReview: "advisory", agent: { command: "no-such-agent-xyz" } });
  r.commit("b.js", "2\n", "feat: add b");
  assert.match(r.cli(["review"]).out, /skipped: no-such-agent-xyz not found/);
  const r2 = makeRepo(t, { aiReview: "advisory", baseBranch: "origin/nope" });
  r2.commit("b.js", "2\n", "feat: add b");
  assert.match(r2.cli(["review"]).out, /failed: base branch origin\/nope not found/);
});

test("review: no changes vs base is skipped", t => {
  const r = makeRepo(t, { aiReview: "advisory" });
  assert.match(r.cli(["review"], { FAKE_AGENT_LOG: r.log }).out, /skipped: no commits/);
  assert.equal(r.calls().length, 0);
});

test("aiReview required: push blocked until the review matches HEAD", t => {
  const r = makeRepo(t, { aiReview: "required" });
  r.commit("b.js", "2\n", "feat: add b");
  let p = r.g("push", "-q", "-u", "origin", "feat/export");
  assert.notEqual(p.code, 0);
  assert.match(p.out, /no AI review has been run/);
  assert.equal(r.cli(["review"]).code, 0);
  p = r.g("push", "-q", "-u", "origin", "feat/export");
  assert.equal(p.code, 0, p.out);
  r.commit("c.js", "3\n", "feat: add c");
  p = r.g("push", "-q");
  assert.notEqual(p.code, 0);
  assert.match(p.out, /code changed since the review/);
});

test("aiReview advisory: stale review only warns", t => {
  const r = makeRepo(t, { aiReview: "advisory" });
  r.commit("b.js", "2\n", "feat: add b");
  const p = r.g("push", "-q", "-u", "origin", "feat/export");
  assert.equal(p.code, 0, p.out);
  assert.match(p.out, /WARN  AI review \(advisory\)/);
});

test("check --json is machine readable and fails on problems", t => {
  const r = makeRepo(t);
  r.g("commit", "-q", "--allow-empty", "--no-verify", "-m", "bad message");
  const out = r.cli(["check", "--json"]);
  assert.equal(out.code, 1);
  const j = JSON.parse(out.out);
  assert.equal(j.branch, "feat/export");
  assert.equal(j.results.find(x => x.name === "Commit messages").status, "fail");
});

test("concurrent review is skipped while one is running", async t => {
  const r = makeRepo(t, { aiReview: "advisory", agentTimeoutSeconds: 8 });
  r.commit("b.js", "2\n", "feat: add b");
  const { spawn } = await import("node:child_process");
  const first = spawn(process.execPath, [path.join(r.work, "review-hooks", "bin", "review-hooks.mjs"), "review"],
    { cwd: r.work, env: { ...process.env, FAKE_AGENT_MODE: "hang" }, stdio: "ignore" });
  const done = new Promise(res => first.on("close", res));
  const state = path.join(r.work, ".git", "review-hooks");
  for (let i = 0; i < 100 && !(fs.existsSync(state) && fs.readdirSync(state).some(f => f.endsWith(".lock"))); i++)
    await new Promise(res => setTimeout(res, 100));
  const second = r.cli(["review"]);
  assert.match(second.out, /already running/);
  await done;
  assert.match(r.cli(["status"]).out, /timed out/);
});
