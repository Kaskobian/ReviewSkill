// review-hooks/tests/deps-e2e.test.mjs - the dependency check through the real
// CLI and the real pre-push hook, against a local fake OSV/KEV server (offline).
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const kit = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

// Async on purpose: the fake server lives in this process, so a blocking
// spawnSync would stop it from answering the hook.
function run(cwd, cmd, args, env = {}) {
  return new Promise(resolve => {
    const p = spawn(cmd, args, { cwd, windowsHide: true,
      env: { ...process.env, GIT_TERMINAL_PROMPT: "0", NO_COLOR: "1", ...env } });
    let out = "";
    p.stdout.on("data", d => { out += d; });
    p.stderr.on("data", d => { out += d; });
    p.on("close", code => resolve({ code, out }));
  });
}

/** Fake OSV + KEV: lodash 4.17.15 has one critical advisory fixed in 4.17.21. */
async function fakeServer(t) {
  const hits = [];
  const server = http.createServer((req, res) => {
    let body = "";
    req.on("data", d => { body += d; });
    req.on("end", () => {
      hits.push(req.url);
      const send = o => { res.writeHead(200, { "Content-Type": "application/json" }); res.end(JSON.stringify(o)); };
      if (req.url === "/osv/querybatch") {
        const { queries } = JSON.parse(body);
        return send({ results: queries.map(q => ({ vulns: q.package.name === "lodash" && q.version === "4.17.15" ? [{ id: "GHSA-test", modified: "m" }] : [] })) });
      }
      if (req.url === "/osv/vulns/GHSA-test") return send({
        id: "GHSA-test", aliases: ["CVE-2021-0001"], summary: "Command injection", modified: "m",
        severity: [{ type: "CVSS_V3", score: "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H" }],
        affected: [{ package: { ecosystem: "npm", name: "lodash" }, ranges: [{ events: [{ introduced: "0" }, { fixed: "4.17.21" }] }] }],
      });
      if (req.url === "/kev") return send({ vulnerabilities: [] });
      res.writeHead(404); res.end("{}");
    });
  });
  await new Promise(r => server.listen(0, "127.0.0.1", r));
  t.after(() => server.close());
  const base = `http://127.0.0.1:${server.address().port}`;
  return { hits, env: { REVIEW_HOOKS_OSV_URL: base + "/osv", REVIEW_HOOKS_KEV_URL: base + "/kev", REVIEW_HOOKS_NVD_URL: base + "/nvd" } };
}

async function makeRepo(t, env) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "rh-deps-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const remote = path.join(dir, "remote.git"), work = path.join(dir, "work");
  await run(dir, "git", ["init", "-q", "--bare", "-b", "main", remote]);
  await run(dir, "git", ["clone", "-q", remote, work]);
  const g = (...a) => run(work, "git", a, env);
  for (const [k, v] of [["user.name", "Test"], ["user.email", "t@example.com"], ["core.autocrlf", "false"], ["commit.gpgsign", "false"]])
    await g("config", k, v);
  fs.cpSync(kit, path.join(work, "review-hooks"), { recursive: true, filter: s => !s.includes(`${path.sep}tests${path.sep}`) });
  const lock = pkgs => JSON.stringify({ lockfileVersion: 3, packages: Object.fromEntries(Object.entries(pkgs).map(([n, v]) => [`node_modules/${n}`, { version: v }])) });
  const write = (f, s) => fs.writeFileSync(path.join(work, f), s);
  write("package-lock.json", lock({ express: "4.18.2" }));
  await g("add", "-A"); await g("commit", "-qm", "chore: initial commit"); await g("push", "-q", "-u", "origin", "main");
  assert.equal((await run(work, process.execPath, ["review-hooks/bin/review-hooks.mjs", "install"])).code, 0);
  await g("checkout", "-q", "-b", "feat/deps");
  const commit = async (file, text, msg) => { write(file, text); await g("add", "-A"); return g("commit", "-qm", msg); };
  const cli = (...a) => run(work, process.execPath, ["review-hooks/bin/review-hooks.mjs", ...a], env);
  return { work, g, commit, cli, lock, write };
}

test("pre-push blocks a branch that introduces a critical, and names the fix", async t => {
  const srv = await fakeServer(t);
  const r = await makeRepo(t, srv.env);
  await r.commit("package-lock.json", r.lock({ express: "4.18.2", lodash: "4.17.15" }), "feat: add lodash");
  const push = await r.g("push", "-q", "-u", "origin", "feat/deps");
  assert.notEqual(push.code, 0, push.out);
  assert.match(push.out, /FAIL  No known-vulnerable dependencies introduced: 1 vulnerable package\(s\) introduced by this branch: lodash@4\.17\.15 \(1 critical\) -> upgrade to 4\.17\.21/);
  assert.match(push.out, /Push blocked/);
  // Fix it and push again
  await r.commit("package-lock.json", r.lock({ express: "4.18.2", lodash: "4.17.21" }), "fix(deps): upgrade lodash to 4.17.21");
  const push2 = await r.g("push", "-q", "-u", "origin", "feat/deps");
  // The first, vulnerable commit is still in the pushed range, but the check is
  // about the tip: 4.17.21 is what ships.
  assert.equal(push2.code, 0, push2.out);
});

test("pre-push does not touch the network when no dependency file changed", async t => {
  const srv = await fakeServer(t);
  const r = await makeRepo(t, srv.env);
  await r.commit("app.js", "console.log(1);\n", "feat: add app");
  const before = srv.hits.length;
  const push = await r.g("push", "-q", "-u", "origin", "feat/deps");
  assert.equal(push.code, 0, push.out);
  assert.equal(srv.hits.length, before, "no OSV calls");
  assert.doesNotMatch(push.out, /vulnerable dependencies/);
});

test("a vulnerability already on main warns but does not block", async t => {
  const srv = await fakeServer(t);
  const r = await makeRepo(t, srv.env);
  await r.g("checkout", "-q", "main");
  await r.commit("package-lock.json", r.lock({ express: "4.18.2", lodash: "4.17.15" }), "chore: old lodash");
  await r.g("push", "-q", "--no-verify", "origin", "main");
  await r.g("checkout", "-q", "-b", "feat/other");
  await r.commit("package-lock.json", r.lock({ express: "4.18.2", lodash: "4.17.15", ms: "2.1.3" }), "feat: add ms");
  const push = await r.g("push", "-q", "-u", "origin", "feat/other");
  assert.equal(push.code, 0, push.out);
  assert.match(push.out, /WARN  No known-vulnerable dependencies introduced: 1 package\(s\) to review \(1 already in the base branch\)/);
});

test("deps command, --json and --no-deps", async t => {
  const srv = await fakeServer(t);
  const r = await makeRepo(t, srv.env);
  await r.commit("package-lock.json", r.lock({ lodash: "4.17.15" }), "feat: add lodash");
  const text = await r.cli("deps");
  assert.equal(text.code, 1);
  assert.match(text.out, /FAIL lodash@4\.17\.15 \[npm\] package-lock\.json  \(introduced by this branch\)/);
  assert.match(text.out, /-> upgrade to 4\.17\.21/);
  const json = JSON.parse((await r.cli("deps", "--json")).out);
  assert.equal(json.status, "fail");
  assert.equal(json.findings[0].cves[0], "CVE-2021-0001");
  const check = await r.cli("check", "--no-deps");
  assert.doesNotMatch(check.out, /vulnerable dependencies/);
});

test("OSV unreachable: warning by default, failure with offline:fail", async t => {
  const env = { REVIEW_HOOKS_OSV_URL: "http://127.0.0.1:9/osv", REVIEW_HOOKS_KEV_URL: "http://127.0.0.1:9/kev" };
  const r = await makeRepo(t, env);
  await r.commit("package-lock.json", r.lock({ lodash: "4.17.15" }), "feat: add lodash");
  const warn = await r.cli("deps");
  assert.equal(warn.code, 0);
  assert.match(warn.out, /OSV\.dev unreachable .*dependencies NOT checked/);
  r.write(".review-hooks.json", JSON.stringify({ dependencies: { offline: "fail" } }));
  await r.g("add", "-A"); await r.g("commit", "-qm", "chore: strict deps");
  const fail = await r.cli("deps");
  assert.equal(fail.code, 1);
});
