// review-hooks/tests/deps.test.mjs - run with: node --test review-hooks/tests/
// Offline tests for the dependency check: parsers, CVSS, policy, network failures.
// A fake `fetch` serves canned OSV / NVD / KEV responses; no real network.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import * as L from "../lib/deps/lockfiles.mjs";
import { cvss3Score, compareVersions, fixedVersion, nvdLookup, nvdSummary } from "../lib/deps/sources.mjs";
import { checkDependencies, summarize } from "../lib/deps/check.mjs";

const names = r => r.map(p => `${p.ecosystem}:${p.name}@${p.version}`).sort();

// ── parsers ──────────────────────────────────────────────────────────────────
test("npm package-lock v3: registry packages only, scoped names, links skipped", () => {
  const lock = JSON.stringify({ lockfileVersion: 3, packages: {
    "": { name: "app" },
    "node_modules/lodash": { version: "4.17.15" },
    "node_modules/@scope/pkg": { version: "1.0.0" },
    "node_modules/a/node_modules/b": { version: "2.0.0" },
    "node_modules/local": { link: true, resolved: "packages/local" },
    "node_modules/fromgit": { version: "1.0.0", resolved: "git+https://github.com/x/y.git#abc" },
    "packages/local": { version: "0.0.1" },
  } });
  assert.deepEqual(names(L.parsePackageLock(lock)), ["npm:@scope/pkg@1.0.0", "npm:b@2.0.0", "npm:lodash@4.17.15"]);
});
test("npm package-lock v1 with aliases", () => {
  const lock = JSON.stringify({ lockfileVersion: 1, dependencies: {
    lodash: { version: "4.17.15", dependencies: { minimist: { version: "0.0.8" } } },
    old: { version: "npm:left-pad@1.1.0" }, gitdep: { version: "github:x/y#abc" } } });
  assert.deepEqual(names(L.parsePackageLock(lock)), ["npm:left-pad@1.1.0", "npm:lodash@4.17.15", "npm:minimist@0.0.8"]);
});
test("pnpm-lock v5, v6 and v9 keys", () => {
  const v5 = "lockfileVersion: 5.4\npackages:\n  /lodash/4.17.15:\n    resolution: {}\n  /@babel/core/7.0.0_supports-color@5.5.0:\n    dev: true\n";
  const v9 = "lockfileVersion: '9.0'\nimporters:\n  .:\n    dependencies: {}\npackages:\n  lodash@4.17.15:\n    resolution: {}\n  '@types/node@20.1.0':\n    resolution: {}\n  react-dom@18.2.0(react@18.2.0):\n    resolution: {}\nsnapshots:\n  lodash@4.17.15: {}\n";
  assert.deepEqual(names(L.parsePnpmLock(v5)), ["npm:@babel/core@7.0.0", "npm:lodash@4.17.15"]);
  assert.deepEqual(names(L.parsePnpmLock(v9)), ["npm:@types/node@20.1.0", "npm:lodash@4.17.15", "npm:react-dom@18.2.0"]);
});
test("yarn.lock classic and berry", () => {
  const classic = '# yarn lockfile v1\n\nlodash@^4.17.0, lodash@^4.17.15:\n  version "4.17.15"\n  resolved "x"\n\n"@scope/a@^1.0.0":\n  version "1.2.3"\n';
  const berry = '__metadata:\n  version: 6\n\n"lodash@npm:^4.17.0":\n  version: 4.17.21\n\n"app@workspace:.":\n  version: 0.0.0-use.local\n';
  assert.deepEqual(names(L.parseYarnLock(classic)), ["npm:@scope/a@1.2.3", "npm:lodash@4.17.15"]);
  assert.deepEqual(names(L.parseYarnLock(berry)), ["npm:lodash@4.17.21"]);
});
test("NuGet: csproj attribute/element, CPM props, packages.config, lock file; ranges and $(vars) skipped", () => {
  const csproj = `<Project><ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="12.0.1" />
    <PackageReference Include="Serilog"><Version>2.10.0</Version></PackageReference>
    <PackageReference Include="Exact" Version="[1.2.3]" />
    <PackageReference Include="Range" Version="[1.0,2.0)" />
    <PackageReference Include="Var" Version="$(V)" />
    <PackageReference Include="Wild" Version="1.*" />
    <PackageReference Include="Central" />
  </ItemGroup></Project>`;
  assert.deepEqual(names(L.parseNugetProject(csproj)), ["NuGet:Exact@1.2.3", "NuGet:Newtonsoft.Json@12.0.1", "NuGet:Serilog@2.10.0"]);
  assert.deepEqual(names(L.parseNugetProject('<Project><ItemGroup><PackageVersion Include="Central" Version="3.0.0" /></ItemGroup></Project>')), ["NuGet:Central@3.0.0"]);
  assert.deepEqual(names(L.parseNugetProject('<packages><package id="jQuery" version="1.8.0" targetFramework="net45" /></packages>')), ["NuGet:jQuery@1.8.0"]);
  const lock = JSON.stringify({ version: 1, dependencies: { "net8.0": {
    "Newtonsoft.Json": { type: "Direct", resolved: "12.0.1" }, "My.Lib": { type: "Project" } } } });
  assert.deepEqual(names(L.parseNugetLock(lock)), ["NuGet:Newtonsoft.Json@12.0.1"]);
});
test("Python: requirements pins only, names normalised; poetry, uv and Pipfile locks", () => {
  const req = "Django==3.2.0\nrequests>=2.0\nPyYAML==5.3  # pin\nzope.interface === 5.0 \\\n  --hash=sha256:abc\n-r other.txt\ngit+https://x/y.git#egg=z\nuvicorn[standard]==0.20.0 ; python_version>'3.8'\n";
  assert.deepEqual(names(L.parseRequirements(req)), ["PyPI:django@3.2.0", "PyPI:pyyaml@5.3", "PyPI:uvicorn@0.20.0", "PyPI:zope-interface@5.0"]);
  const poetry = '[[package]]\nname = "Django"\nversion = "3.2.0"\n\n[[package]]\nname = "mylib"\nversion = "0.1.0"\n\n[package.source]\ntype = "directory"\nurl = "../mylib"\n';
  assert.deepEqual(names(L.parsePoetryOrUvLock(poetry)), ["PyPI:django@3.2.0"]);
  const uv = '[[package]]\nname = "app"\nversion = "0.1.0"\nsource = { editable = "." }\n\n[[package]]\nname = "pyyaml"\nversion = "5.3"\nsource = { registry = "https://pypi.org/simple" }\n';
  assert.deepEqual(names(L.parsePoetryOrUvLock(uv)), ["PyPI:pyyaml@5.3"]);
  assert.deepEqual(names(L.parsePipfileLock(JSON.stringify({ default: { django: { version: "==3.2.0" } }, develop: { pytest: { version: "==6.0.0" } } }))), ["PyPI:django@3.2.0", "PyPI:pytest@6.0.0"]);
});
test("Go, Cargo, Composer, Gemfile, Gradle", () => {
  assert.deepEqual(names(L.parseGoMod("module x\n\ngo 1.21\n\nrequire golang.org/x/text v0.3.5\nrequire (\n\tgithub.com/a/b v1.2.3 // indirect\n)\n")), ["Go:github.com/a/b@v1.2.3", "Go:golang.org/x/text@v0.3.5"]);
  assert.deepEqual(names(L.parseCargoLock('[[package]]\nname = "tokio"\nversion = "1.8.0"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\n\n[[package]]\nname = "mycrate"\nversion = "0.1.0"\n')), ["crates.io:tokio@1.8.0"]);
  assert.deepEqual(names(L.parseComposerLock(JSON.stringify({ packages: [{ name: "laravel/framework", version: "v8.0.0" }], "packages-dev": [{ name: "x/y", version: "dev-main" }] }))), ["Packagist:laravel/framework@8.0.0"]);
  assert.deepEqual(names(L.parseGemfileLock("GEM\n  remote: https://rubygems.org/\n  specs:\n    rails (6.0.0)\n      actionpack (= 6.0.0)\n    nokogiri (1.10.0-x86_64-linux)\n\nPLATFORMS\n  ruby\n")), ["RubyGems:nokogiri@1.10.0", "RubyGems:rails@6.0.0"]);
  assert.deepEqual(names(L.parseGradleLockfile("# comment\ncom.fasterxml.jackson.core:jackson-databind:2.9.8=compileClasspath\nempty=\n")), ["Maven:com.fasterxml.jackson.core:jackson-databind@2.9.8"]);
});
test("file detection skips vendored folders; bad files return an error instead of throwing", () => {
  assert.equal(L.isDependencyFile("package-lock.json"), true);
  assert.equal(L.isDependencyFile("src/Api/Api.csproj"), true);
  assert.equal(L.isDependencyFile("node_modules/x/package-lock.json"), false);
  assert.equal(L.isDependencyFile("Api/bin/Debug/packages.lock.json"), false);
  assert.equal(L.isDependencyFile("README.md"), false);
  const r = L.parseDependencyFile("package-lock.json", "{ not json");
  assert.deepEqual(r.packages, []);
  assert.match(r.error, /package-lock\.json/);
  assert.equal(L.parseDependencyFile("x.csproj", "\uFEFF<Project><PackageReference Include=\"A\" Version=\"1.0.0\"/></Project>").packages.length, 1);
});

// ── versions and scores ──────────────────────────────────────────────────────
test("CVSS 3.x base score matches the FIRST calculator", () => {
  for (const [v, s] of [
    ["CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H", 10.0], ["CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", 9.8],
    ["CVSS:3.1/AV:N/AC:L/PR:H/UI:N/S:U/C:H/I:H/A:H", 7.2], ["CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N", 6.1],
    ["CVSS:3.0/AV:L/AC:H/PR:L/UI:R/S:U/C:L/I:N/A:N", 2.2], ["CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N", 0]])
    assert.equal(cvss3Score(v), s, v);
  assert.equal(cvss3Score("CVSS:4.0/AV:N"), null);
  assert.equal(cvss3Score("garbage"), null);
});
test("version compare and fixed-version choice", () => {
  assert.ok(compareVersions("1.10.0", "1.9.0") > 0);
  assert.ok(compareVersions("1.0.0", "1.0.0-rc1") > 0);
  assert.ok(compareVersions("v0.3.7", "v0.3.5") > 0);
  assert.equal(compareVersions("2.0", "2.0.0"), 0);
  const rec = { affected: [
    { package: { ecosystem: "npm", name: "lodash" }, ranges: [{ events: [{ introduced: "0" }, { fixed: "4.17.21" }] }] },
    { package: { ecosystem: "npm", name: "lodash" }, ranges: [{ events: [{ introduced: "3.0.0" }, { fixed: "3.10.2" }] }] },
    { package: { ecosystem: "npm", name: "lodash-es" }, ranges: [{ events: [{ fixed: "9.9.9" }] }] }] };
  assert.equal(fixedVersion(rec, { ecosystem: "npm", name: "lodash", version: "4.17.15" }), "4.17.21");
  assert.equal(fixedVersion(rec, { ecosystem: "npm", name: "lodash", version: "4.17.21" }), null);
});
test("NVD summary prefers CVSS 4 / 3.1 Primary and keeps KEV", () => {
  const s = nvdSummary({ id: "CVE-1", vulnStatus: "Analyzed", cisaExploitAdd: "2021-12-10", cisaActionDue: "2021-12-24",
    metrics: { cvssMetricV31: [{ type: "Secondary", cvssData: { version: "3.1", baseScore: 5, baseSeverity: "MEDIUM" } },
                               { type: "Primary", cvssData: { version: "3.1", baseScore: 10, baseSeverity: "CRITICAL" } }],
               cvssMetricV2: [{ type: "Primary", cvssData: { baseScore: 9.3 }, baseSeverity: "HIGH" }] },
    weaknesses: [{ description: [{ value: "CWE-502" }, { value: "NVD-CWE-Other" }] }] });
  assert.deepEqual([s.score, s.severity, s.cwes, s.kev.added], [10, "critical", ["CWE-502"], "2021-12-10"]);
});

// ── NVD client: pacing, bad key, outage ──────────────────────────────────────
function fakeClock() { let t = 0; return { now: () => t, wait: async ms => { t += ms; }, get t() { return t; } }; }
const json = (body, status = 200, headers = {}) => ({ ok: status < 400, status, json: async () => body, headers: { get: h => headers[h.toLowerCase()] } });
const nvdBody = (id, score) => ({ vulnerabilities: [{ cve: { id, metrics: { cvssMetricV31: [{ type: "Primary", cvssData: { version: "3.1", baseScore: score, baseSeverity: score >= 9 ? "CRITICAL" : "HIGH" } }] } } }] });

test("NVD: 6 s between requests without a key, 0.7 s with one, cap per run", async () => {
  for (const [key, gap] of [[undefined, 6000], ["11111111-2222-3333-4444-555555555555", 700]]) {
    const clock = fakeClock(); const seen = [];
    const http = async (url, o) => { seen.push(o.headers.apiKey); return json(nvdBody(new URL(url).searchParams.get("cveId"), 7.5)); };
    const r = await nvdLookup(["CVE-1", "CVE-2", "CVE-3", "CVE-4"], { http, apiKey: key, maxLookups: 3, ...clock });
    assert.equal(r.byId.size, 3);
    assert.equal(clock.t, gap * 2);
    assert.deepEqual(seen, [key, key, key]);
    assert.match(r.notes.join(), /1 CVE\(s\) not looked up/);
  }
});
test("NVD: rejected key falls back to no key; outage stops politely", async () => {
  const clock = fakeClock(); let calls = 0;
  const http = async (url, o) => { calls++; return o.headers.apiKey ? json({}, 404, { message: "Invalid apiKey." }) : json(nvdBody("CVE-1", 9.8)); };
  const r = await nvdLookup(["CVE-1"], { http, apiKey: "00000000-0000-0000-0000-000000000000", ...clock });
  assert.equal(r.byId.get("CVE-1").score, 9.8);
  assert.match(r.notes.join(), /rejected NVD_API_KEY/);
  assert.equal(calls, 2);
  let n = 0;
  const down = await nvdLookup(["CVE-1", "CVE-2", "CVE-3"], { http: async () => { n++; return json({}, 503); }, ...fakeClock() });
  assert.equal(n, 1, "stops after the first failure");
  assert.match(down.notes.join(), /NVD unreachable \(HTTP 503\)/);
  assert.match((await nvdLookup(["CVE-1"], { http, apiKey: "not-a-key", ...fakeClock() })).notes.join(), /not a valid key format/);
});

// ── end to end on a real git repo with a fake network ────────────────────────
function repo(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "deps-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const g = (...a) => { const r = spawnSync("git", a, { cwd: dir, encoding: "utf8" }); if (r.status) throw new Error(r.stderr); return r.stdout.trim(); };
  g("init", "-q", "-b", "main"); g("config", "user.email", "t@example.com"); g("config", "user.name", "t"); g("config", "core.autocrlf", "false");
  const write = (f, s) => { fs.mkdirSync(path.dirname(path.join(dir, f)), { recursive: true }); fs.writeFileSync(path.join(dir, f), s); };
  const commit = m => { g("add", "-A"); g("commit", "-qm", m); return g("rev-parse", "HEAD"); };
  return { dir, g, write, commit };
}
const lockWith = pkgs => JSON.stringify({ lockfileVersion: 3, packages: Object.fromEntries(Object.entries(pkgs).map(([n, v]) => [`node_modules/${n}`, { version: v }])) });

/** OSV knows: lodash 4.17.15 (critical via CVSS vector, fixed 4.17.21), log4js 6.3.0 (medium, KEV), nofix 1.0.0 (high, no fix). */
function fakeNet({ osvDown = false, kevDown = false, calls = [] } = {}) {
  const VULNS = {
    "GHSA-crit": { id: "GHSA-crit", aliases: ["CVE-2021-0001", "PYSEC-x"], summary: "Command injection", modified: "m1",
      severity: [{ type: "CVSS_V3", score: "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H" }],
      affected: [{ package: { ecosystem: "npm", name: "lodash" }, ranges: [{ events: [{ introduced: "0" }, { fixed: "4.17.21" }] }] }] },
    "PYSEC-x": { id: "PYSEC-x", aliases: ["GHSA-crit", "CVE-2021-0001"], summary: "duplicate of GHSA-crit", modified: "m1", affected: [] },
    "GHSA-kev": { id: "GHSA-kev", aliases: ["CVE-2021-0002"], summary: "Exploited bug", modified: "m1", database_specific: { severity: "MODERATE" },
      affected: [{ package: { ecosystem: "npm", name: "log4js" }, ranges: [{ events: [{ introduced: "0" }, { fixed: "6.4.0" }] }] }] },
    "GHSA-nofix": { id: "GHSA-nofix", aliases: [], summary: "Unfixed", modified: "m1", database_specific: { severity: "HIGH" },
      affected: [{ package: { ecosystem: "npm", name: "nofix" }, ranges: [{ events: [{ introduced: "0" }] }] }] },
  };
  const AFFECTED = { "lodash@4.17.15": ["GHSA-crit", "PYSEC-x"], "log4js@6.3.0": ["GHSA-kev"], "nofix@1.0.0": ["GHSA-nofix"] };
  return async (url, o = {}) => {
    calls.push(url);
    if (url.includes("api.osv.dev")) {
      if (osvDown) throw new TypeError("fetch failed");
      if (url.endsWith("/querybatch")) {
        const { queries } = JSON.parse(o.body);
        return json({ results: queries.map(q => ({ vulns: (AFFECTED[`${q.package.name}@${q.version}`] || []).map(id => ({ id, modified: "m1" })) })) });
      }
      const id = decodeURIComponent(url.split("/vulns/")[1]);
      return VULNS[id] ? json(VULNS[id]) : json({}, 404);
    }
    if (url.includes("cisa.gov")) return kevDown ? json({}, 500) : json({ vulnerabilities: [{ cveID: "CVE-2021-0002" }] });
    if (url.includes("nvd.nist.gov")) return json({ vulnerabilities: [] });
    throw new Error("unexpected " + url);
  };
}

async function run(t, { base, head, policy, net, cacheDir } = {}) {
  const r = repo(t);
  r.write("package-lock.json", lockWith(base)); const b = r.commit("base");
  r.write("package-lock.json", lockWith(head)); const h = r.commit("head");
  const prev = process.cwd(); process.chdir(r.dir);
  try { return await checkDependencies({ head: h, base: b, policy, http: net || fakeNet(), cacheDir, wait: async () => {} }); }
  finally { process.chdir(prev); }
}

test("e2e: an introduced critical fails, with the fix version; aliases counted once", async t => {
  const rep = await run(t, { base: { ok: "1.0.0" }, head: { ok: "1.0.0", lodash: "4.17.15" } });
  assert.equal(rep.status, "fail");
  const f = rep.findings.filter(x => x.package === "lodash");
  assert.equal(f.length, 1, "GHSA and PYSEC aliases merged");
  assert.deepEqual([f[0].severity, f[0].score, f[0].fixed, f[0].introduced, f[0].decision], ["critical", 9.8, "4.17.21", true, "fail"]);
  assert.match(summarize(rep), /lodash@4\.17\.15 .*-> upgrade to 4\.17\.21/);
});
test("e2e: the same vulnerability already in the target only warns", async t => {
  const rep = await run(t, { base: { lodash: "4.17.15" }, head: { lodash: "4.17.15", ok: "1.0.0" } });
  assert.equal(rep.status, "warn");
  assert.equal(rep.findings[0].introduced, false);
  assert.match(summarize(rep), /already in the base branch/);
});
test("e2e: a medium in CISA KEV fails when introduced; failOnKev:false makes it a warning", async t => {
  assert.equal((await run(t, { base: {}, head: { log4js: "6.3.0" } })).status, "fail");
  const rep = await run(t, { base: {}, head: { log4js: "6.3.0" }, policy: { failOnKev: false } });
  assert.equal(rep.status, "warn");
  assert.equal(rep.findings[0].kev, true);
});
test("e2e: failOn threshold and unfixable advisories", async t => {
  const strict = await run(t, { base: {}, head: { nofix: "1.0.0" }, policy: { failOn: "high" } });
  assert.equal(strict.status, "fail");
  assert.equal(strict.findings[0].fixed, null);
  assert.match(summarize(strict), /no fixed version known/);
  assert.equal((await run(t, { base: {}, head: { nofix: "1.0.0" } })).status, "warn");
});
test("e2e: exceptions need a reason and an expiry date", async t => {
  const future = "2999-01-01", past = "2000-01-01";
  const ok = await run(t, { base: {}, head: { lodash: "4.17.15" }, policy: { ignore: [{ id: "CVE-2021-0001", reason: "not reachable: template() unused", until: future }] } });
  assert.equal(ok.status, "pass");
  assert.equal(ok.findings[0].decision, "ignored");
  const expired = await run(t, { base: {}, head: { lodash: "4.17.15" }, policy: { ignore: [{ id: "GHSA-crit", reason: "x", until: past }] } });
  assert.equal(expired.status, "fail");
  assert.match(expired.notes.join(), /expired/);
  const noReason = await run(t, { base: {}, head: { lodash: "4.17.15" }, policy: { ignore: [{ id: "GHSA-crit" }] } });
  assert.equal(noReason.status, "fail");
  assert.match(noReason.notes.join(), /no "reason"/);
});
test("e2e: OSV down is a warning by default and a failure if configured; KEV down is noted", async t => {
  const warn = await run(t, { base: {}, head: { lodash: "4.17.15" }, net: fakeNet({ osvDown: true }) });
  assert.equal(warn.status, "warn");
  assert.match(warn.notes.join(), /OSV\.dev unreachable/);
  assert.equal((await run(t, { base: {}, head: { lodash: "4.17.15" }, net: fakeNet({ osvDown: true }), policy: { offline: "fail" } })).status, "fail");
  const kev = await run(t, { base: {}, head: { log4js: "6.3.0" }, net: fakeNet({ kevDown: true }) });
  assert.match(kev.notes.join(), /CISA KEV catalog unavailable/);
});
test("e2e: second run is served from cache", async t => {
  const cacheDir = fs.mkdtempSync(path.join(os.tmpdir(), "deps-cache-"));
  t.after(() => fs.rmSync(cacheDir, { recursive: true, force: true }));
  const calls1 = [], calls2 = [];
  await run(t, { base: {}, head: { lodash: "4.17.15" }, net: fakeNet({ calls: calls1 }), cacheDir });
  const rep = await run(t, { base: {}, head: { lodash: "4.17.15" }, net: fakeNet({ calls: calls2 }), cacheDir });
  assert.equal(rep.status, "fail");
  assert.ok(calls1.length > 0);
  assert.deepEqual(calls2, [], "no network on a warm cache");
});
test("e2e: no dependency files passes quietly; invalid policy is rejected", async t => {
  const r = repo(t); r.write("a.js", "1"); const h = r.commit("x");
  const prev = process.cwd(); process.chdir(r.dir);
  try {
    const rep = await checkDependencies({ head: h, base: null, http: fakeNet() });
    assert.equal(rep.status, "pass");
    await assert.rejects(checkDependencies({ head: h, base: null, http: fakeNet(), policy: { failOn: "severe" } }), /failOn/);
  } finally { process.chdir(prev); }
});
