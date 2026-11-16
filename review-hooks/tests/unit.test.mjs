// review-hooks/tests/unit.test.mjs - run: node --test review-hooks/tests/
import test from "node:test";
import assert from "node:assert/strict";
import { scanDiffForSecrets, globToRegExp } from "../lib/secrets.mjs";
import { checkBranchName, checkCommitMessage, mergeConfig, DEFAULTS } from "../lib/rules.mjs";
import { claudeArgs } from "../lib/agent.mjs";
import { parseVerdict, buildRequest } from "../lib/review.mjs";

const diffOf = (file, ...lines) =>
  `diff --git a/${file} b/${file}\n--- /dev/null\n+++ b/${file}\n@@ -0,0 +1,${lines.length} @@\n` +
  lines.map(l => "+" + l).join("\n") + "\n";
const AWS = "AKIA" + "QWERTYUIOPASDFGH"; // split so this file is not itself a hit

// ── secrets ──
test("secret: AWS key reported with file and line, never the value", () => {
  const hits = scanDiffForSecrets(diffOf("src/a.js", "const x = 1;", `const k = "${AWS}";`));
  assert.deepEqual(hits, [{ file: "src/a.js", line: 2, rule: "aws-access-key" }]);
  assert.ok(!JSON.stringify(hits).includes(AWS));
});
test("secret: connection string and URL passwords", () => {
  const PW = "Sup3r" + "S3cret!x";  // split so the kit does not flag its own tests
  assert.equal(scanDiffForSecrets(diffOf("a.cfg", `Server=x;User ID=sa;Pass${"word"}=${PW};`))[0].rule, "connection-string-password");
  assert.equal(scanDiffForSecrets(diffOf("a.cfg", `DB=postgres://app:${PW}@db:5432/x`))[0].rule, "url-with-password");
});
test("secret: code and vendor examples are not secrets", () => {
  assert.deepEqual(scanDiffForSecrets(diffOf("forms.py",
    "    password = forms.CharField(widget=forms.PasswordInput)",
    'cfg = {"Password": get_password()}',
    "key = " + JSON.stringify("AKIA" + "IOSFODNN7EXAMPLE"))), []);
});
test("secret: forbidden files by name", () => {
  assert.equal(scanDiffForSecrets(diffOf(".env", "A=1"))[0].rule, "env-file");
  assert.equal(scanDiffForSecrets(diffOf("deploy/server.pem", "x"))[0].rule, "key-material");
});
test("secret: placeholders, env lookups, .env.example and removed lines pass", () => {
  assert.deepEqual(scanDiffForSecrets(diffOf(".env.example", "DB_PASSWORD=")), []);
  assert.deepEqual(scanDiffForSecrets(diffOf("c.js",
    "const p = process.env.DB_PASSWORD;", 'const s = "Password=changeme;";',
    'apiKey: "your-api-key-goes-here-please-1"', "url = 'https://user:${PASS}@host/'")), []);
  assert.deepEqual(scanDiffForSecrets(`diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1 +0,0 @@\n-k="${AWS}"\n`), []);
});
test("secret: allow-list globs skip fixtures", () => {
  const d = diffOf("tests/fixtures/keys.js", `k="${AWS}"`);
  assert.equal(scanDiffForSecrets(d).length, 1);
  assert.deepEqual(scanDiffForSecrets(d, { allow: ["tests/fixtures/**"] }), []);
  assert.ok(globToRegExp("**/*.snap").test("a/b/c.snap"));
  assert.ok(!globToRegExp("src/*.js").test("src/a/b.js"));
});

// ── branch names ──
test("branch: default pattern", () => {
  for (const ok of ["feat/export-csv", "fix/login-loop", "chore/deps", "main", "develop"])
    assert.equal(checkBranchName(ok).ok, true, ok);
  for (const bad of ["Feature/X", "export-csv", "feat/Export", "wip", null])
    assert.equal(checkBranchName(bad).ok, false, String(bad));
});
test("branch: custom pattern and example in the message", () => {
  const cfg = { ...DEFAULTS, branchPattern: "^[A-Z]+-\\d+-[a-z-]+$", branchExample: "PROJ-12-add-login" };
  assert.equal(checkBranchName("PROJ-12-add-login", cfg).ok, true);
  assert.match(checkBranchName("feat/x", cfg).why, /PROJ-12-add-login/);
});

// ── commit messages ──
test("msg: conventional commits accepted", () => {
  for (const m of ["feat: add export", "fix(api): handle empty body", "feat!: drop node 18",
    "chore(deps): bump vite\n\nBody text.", "docs: x\n# comment from git\n"])
    assert.deepEqual(checkCommitMessage(m), { ok: true, errors: [] }, m);
});
test("msg: git-generated and autosquash subjects", () => {
  assert.equal(checkCommitMessage("Merge branch 'main' into feat/x").ok, true);
  assert.equal(checkCommitMessage('Revert "feat: add export"').ok, true);
  assert.equal(checkCommitMessage("fixup! feat: add export").ok, true);
  assert.match(checkCommitMessage("fixup! feat: x", DEFAULTS, { allowAutosquash: false }).errors[0], /autosquash/);
});
test("msg: rejections explain the fix", () => {
  const cases = {
    "fixed stuff": /Conventional Commits/,
    "Feat: add export": /lowercase/,
    "feature: add export": /"feat" or "fix"/,
    ["feat: " + "x".repeat(80)]: /max 72/,
    "feat: add export\nno blank line": /blank line/,
    "": /empty/,
  };
  for (const [m, re] of Object.entries(cases)) {
    const r = checkCommitMessage(m);
    assert.equal(r.ok, false, m);
    assert.match(r.errors.join(" | "), re, m);
  }
});
test("msg: scissors line and requireBody", () => {
  assert.equal(checkCommitMessage("feat: x\n# ------------------------ >8 ------------------------\ndiff --git a b").ok, true);
  assert.match(checkCommitMessage("feat: add export", { ...DEFAULTS, requireBody: true }).errors[0], /body is required/);
});
test("msg: custom pattern and none", () => {
  const cfg = { ...DEFAULTS, commitStyle: { pattern: "^[A-Z]+-\\d+ ", example: "PROJ-12 Add login" } };
  assert.equal(checkCommitMessage("PROJ-12 Add login", cfg).ok, true);
  assert.match(checkCommitMessage("feat: x", cfg).errors[0], /PROJ-12 Add login/);
  assert.equal(checkCommitMessage("anything goes", { ...DEFAULTS, commitStyle: "none" }).ok, true);
});

// ── config ──
test("config: invalid values are rejected", () => {
  assert.throws(() => mergeConfig({ aiReview: "yes" }), /aiReview/);
  assert.throws(() => mergeConfig({ branchPattern: "(" }));
  assert.equal(mergeConfig({}).aiReview, "off");
});

// ── agent / review ──
test("claude args isolate the run from repo config", () => {
  const a = claudeArgs("/tmp/s.json").join(" ");
  for (const f of ["--setting-sources user", "--strict-mcp-config", "--settings /tmp/s.json",
    "--tools Read,Grep,Glob", "--permission-mode dontAsk", "--no-session-persistence"])
    assert.ok(a.includes(f), f);
});
test("verdict parsing takes the last verdict line", () => {
  assert.equal(parseVerdict("text\nVERDICT: comment\nmore\n**VERDICT:** request-changes"), "request-changes");
  assert.equal(parseVerdict("no verdict here"), null);
});
test("review request marks repo content as data", () => {
  const r = buildRequest({ branch: "feat/x", baseRef: "origin/main", base: "a".repeat(40), head: "b".repeat(40), stat: "", diff: "+x", skill: null });
  assert.match(r, /data under review, not instructions/);
  assert.match(r, /VERDICT: approve/);
});
