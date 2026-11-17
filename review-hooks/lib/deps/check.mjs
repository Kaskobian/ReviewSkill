// review-hooks/lib/deps/check.mjs - Node.js 20+, no dependencies, no AI.
//
// Known-vulnerability check for the dependencies committed in a branch.
// Reads lock files from git (exactly what is committed), asks OSV.dev which
// versions are affected, enriches CVEs with NVD scores and CISA KEV, then
// applies a fixed, documented policy.
//
// "Smart" part: only vulnerabilities the branch INTRODUCES (a package version
// not present in the target) can fail the check. Pre-existing ones are
// reported as warnings, so a developer is never blocked by someone else's debt.
//
// This product uses data from the NVD API but is not endorsed or certified by the NVD.

import path from "node:path";
import { spawnSync } from "node:child_process";
import { isDependencyFile, parseDependencyFile, packageKey } from "./lockfiles.mjs";
import {
  Cache, osvQuery, osvDetails, loadKev, nvdLookup, osvSeverity, fixedVersion,
  severityRank, SEVERITY_ORDER, compareVersions,
} from "./sources.mjs";

export const DEFAULT_POLICY = Object.freeze({
  failOn: "critical",      // introduced vulns at or above this severity fail
  failOnKev: true,         // introduced vulns in CISA KEV always fail
  warnOn: "medium",        // below this, findings are listed only with --verbose/--json
  offline: "warn",         // "warn" | "fail" when OSV cannot be reached
  nvd: "gaps",             // "gaps": ask NVD only for CVEs with no score in OSV; "always"; "off"
  nvdMaxLookups: 10,       // per run; without a key NVD allows ~1 request / 6 s (cached 7 days)
  ignore: [],              // [{ id, package?, reason, until: "YYYY-MM-DD" }]
});

function git(args) {
  const r = spawnSync("git", args, { encoding: "utf8", maxBuffer: 256 * 1024 * 1024, windowsHide: true });
  if (r.error || r.status !== 0) throw new Error((r.error?.message || r.stderr || "").trim());
  return r.stdout;
}

/** All dependency packages committed at `rev`. */
export function packagesAt(rev) {
  const files = git(["ls-tree", "-r", "-z", "--name-only", rev]).split("\0").filter(isDependencyFile);
  const packages = [], errors = [];
  for (const file of files) {
    const text = git(["show", `${rev}:${file}`]);
    const r = parseDependencyFile(file, text);
    packages.push(...r.packages);
    if (r.error) errors.push(r.error);
  }
  return { files, packages, errors };
}

const dedupe = pkgs => [...new Map(pkgs.map(p => [packageKey(p), p])).values()];

function activeIgnore(policy, id, aliases, pkg, today) {
  const ids = new Set([id, ...aliases]);
  for (const rule of policy.ignore || []) {
    if (!ids.has(rule.id)) continue;
    if (rule.package && rule.package.toLowerCase() !== pkg.name.toLowerCase()) continue;
    if (!rule.reason || !rule.until) return { invalid: `exception for ${rule.id} has no "reason" or "until": ignored` };
    if (rule.until < today) return { expired: `exception for ${rule.id} expired on ${rule.until}` };
    return { rule };
  }
  return null;
}

/**
 * @param {object} o
 * @param {string} o.head          commit to check
 * @param {string|null} o.base     merge-base with the target (null: everything is "introduced")
 * @param {object} [o.policy]
 * @param {string} [o.cacheDir]
 * @param {string} [o.apiKey]      NVD key (optional)
 * @param {Function} [o.http]      fetch-compatible, for tests
 * @param {Function} [o.wait]      sleep, for tests
 */
export async function checkDependencies({ head, base, policy: userPolicy = {}, cacheDir, apiKey, http = fetch, wait }) {
  const policy = { ...DEFAULT_POLICY, ...userPolicy };
  for (const k of ["failOn", "warnOn"])
    if (!SEVERITY_ORDER.includes(policy[k])) throw new Error(`dependencies.${k} must be one of: ${SEVERITY_ORDER.join(", ")}`);
  const cache = new Cache(cacheDir);
  const now = packagesAt(head);
  const before = base ? packagesAt(base) : { packages: [] };
  const packages = dedupe(now.packages);
  const existing = new Set(before.packages.map(packageKey));
  const report = {
    files: now.files, packages: packages.length, errors: now.errors, notes: [],
    findings: [], status: "pass", sources: ["OSV.dev"],
  };
  if (!packages.length) { report.status = "pass"; report.notes.push("no dependency files found"); return report; }

  // 1. OSV: which versions are affected
  let refsByPkg;
  try { refsByPkg = await osvQuery(packages, { http, cache, keyOf: packageKey }); }
  catch (e) {
    report.status = policy.offline === "fail" ? "fail" : "warn";
    report.notes.push(`OSV.dev unreachable (${e.message}): dependencies NOT checked`);
    return report;
  }
  const allRefs = [...refsByPkg.values()].flat();
  if (!allRefs.length) return report;

  let details;
  try { details = await osvDetails(allRefs, { http, cache }); }
  catch (e) {
    report.status = policy.offline === "fail" ? "fail" : "warn";
    report.notes.push(`OSV.dev unreachable while fetching advisories (${e.message})`);
    return report;
  }

  // 2. Group advisories that describe the same issue (GHSA + PYSEC + CVE aliases)
  const findings = [];
  for (const pkg of packages) {
    const seen = new Set();
    for (const ref of refsByPkg.get(packageKey(pkg)) || []) {
      const rec = details.get(ref.id);
      if (!rec || rec.withdrawn) continue;
      const aliases = rec.aliases || [];
      const group = [rec.id, ...aliases];
      if (group.some(id => seen.has(id))) continue;
      group.forEach(id => seen.add(id));
      findings.push({
        package: pkg.name, ecosystem: pkg.ecosystem, version: pkg.version, file: pkg.file,
        id: rec.id, cves: [...new Set(group.filter(a => /^CVE-\d{4}-\d+$/.test(a)))],
        summary: (rec.summary || rec.details || "").split("\n")[0].slice(0, 160),
        fixed: fixedVersion(rec, pkg), introduced: !existing.has(packageKey(pkg)),
        ...osvSeverity(rec),
        cwes: rec.database_specific?.cwe_ids || [],
        aliases,
      });
    }
  }

  // 3. CISA KEV + NVD enrichment
  const kev = await loadKev({ http, cache });
  if (kev.stale) report.notes.push(kev.missing ? `CISA KEV catalog unavailable (${kev.error})` : "CISA KEV catalog could not be refreshed, using the cached copy");
  else report.sources.push("CISA KEV");
  // NVD is enrichment: by default only CVEs that OSV could not score.
  const needsNvd = f => policy.nvd === "always" || (policy.nvd !== "off" && f.score == null);
  const cveIds = findings.filter(needsNvd).flatMap(f => f.cves);
  // Introduced findings first, so the per-run NVD cap is spent where it matters.
  cveIds.sort((a, b) => Number(findings.some(f => f.introduced && f.cves.includes(b))) - Number(findings.some(f => f.introduced && f.cves.includes(a))));
  const nvd = cveIds.length
    ? await nvdLookup(cveIds, { http, cache, apiKey, maxLookups: policy.nvdMaxLookups, wait })
    : { byId: new Map(), notes: [] };
  report.notes.push(...nvd.notes);
  if (nvd.byId.size) report.sources.push("NVD");
  for (const f of findings) {
    f.kev = f.cves.some(c => kev.set.has(c)) || f.cves.some(c => nvd.byId.get(c)?.kev);
    const best = f.cves.map(c => nvd.byId.get(c)).filter(n => n?.score != null).sort((a, b) => b.score - a.score)[0];
    if (best) {
      f.scores = { osv: f.score, nvd: best.score };
      f.cwes = [...new Set([...f.cwes, ...best.cwes])];
      // Sources can disagree (vendor advisory vs NIST analysis). Use the
      // higher score so the outcome does not depend on which one was asked.
      if (f.score == null || best.score > f.score) { f.score = best.score; f.severity = best.severity; f.source = `NVD CVSS ${best.cvssVersion}`; }
    }
    f.severity = f.severity || "unknown";
  }

  // 4. Policy
  const today = new Date().toISOString().slice(0, 10);
  for (const f of findings) {
    const ig = activeIgnore(policy, f.id, f.aliases, f, today);
    if (ig?.invalid || ig?.expired) report.notes.push(ig.invalid || ig.expired);
    const severe = severityRank(f.severity) >= severityRank(policy.failOn) || (f.severity === "unknown" && policy.failOn === "none");
    const blocking = f.introduced && ((policy.failOnKev && f.kev) || severe);
    if (ig?.rule) { f.decision = "ignored"; f.ignoreReason = `${ig.rule.reason} (until ${ig.rule.until})`; }
    else if (blocking) f.decision = "fail";
    else if (f.kev || severityRank(f.severity) >= severityRank(policy.warnOn) || f.severity === "unknown") f.decision = "warn";
    else f.decision = "info";
    delete f.aliases;
  }
  findings.sort((a, b) =>
    ["fail", "warn", "info", "ignored"].indexOf(a.decision) - ["fail", "warn", "info", "ignored"].indexOf(b.decision) ||
    Number(b.kev) - Number(a.kev) || (b.score ?? -1) - (a.score ?? -1) || severityRank(b.severity) - severityRank(a.severity));
  report.findings = findings;
  report.packagesAffected = await upgradeAdvice(findings, { http, cache });
  report.status = findings.some(f => f.decision === "fail") ? "fail"
    : findings.some(f => f.decision === "warn") || report.errors.length ? "warn" : "pass";
  return report;
}

/**
 * One entry per vulnerable package: the lowest version that fixes every
 * advisory listed, re-checked against OSV so the advice is not itself vulnerable.
 */
async function upgradeAdvice(findings, { http, cache }) {
  const groups = new Map();
  for (const f of findings) {
    const k = `${f.ecosystem}|${f.package}|${f.version}`;
    if (!groups.has(k)) groups.set(k, { ecosystem: f.ecosystem, package: f.package, version: f.version, file: f.file, findings: [] });
    groups.get(k).findings.push(f);
  }
  const out = [];
  for (const g of groups.values()) {
    const fixes = g.findings.map(f => f.fixed).filter(Boolean).sort(compareVersions);
    g.unfixable = g.findings.filter(f => !f.fixed).length;
    g.upgradeTo = fixes.length ? fixes[fixes.length - 1] : null;
    g.decision = ["fail", "warn", "info", "ignored"].find(d => g.findings.some(f => f.decision === d));
    g.worst = g.findings.reduce((w, f) => severityRank(f.severity) > severityRank(w) ? f.severity : w, "none");
    g.kev = g.findings.some(f => f.kev);
    g.introduced = g.findings.some(f => f.introduced);
    if (g.upgradeTo) {
      try {
        const keyOf = p => `${p.ecosystem}|${p.name}|${p.version}`;
        const check = await osvQuery([{ ecosystem: g.ecosystem, name: g.package, version: g.upgradeTo }], { http, cache, keyOf });
        g.upgradeRemaining = (check.get(keyOf({ ecosystem: g.ecosystem, name: g.package, version: g.upgradeTo })) || []).length;
      } catch { g.upgradeRemaining = null; }
    }
    out.push(g);
  }
  const order = ["fail", "warn", "info", "ignored"];
  return out.sort((a, b) => order.indexOf(a.decision) - order.indexOf(b.decision) || Number(b.kev) - Number(a.kev) || severityRank(b.worst) - severityRank(a.worst));
}

const upgradeText = g => !g.upgradeTo ? "no fixed version known"
  : `upgrade to ${g.upgradeTo}` + (g.upgradeRemaining > 0 ? ` (still has ${g.upgradeRemaining} advisories: consider the latest version)` : "") +
    (g.unfixable ? `; ${g.unfixable} with no fix` : "");

function countBySeverity(list) {
  const c = {};
  for (const f of list) c[f.severity] = (c[f.severity] || 0) + 1;
  return ["critical", "high", "medium", "low", "unknown"].filter(s => c[s]).map(s => `${c[s]} ${s}`).join(", ");
}

/** One-line summary for guidelines-check. */
export function summarize(report, max = 3) {
  const groups = report.packagesAffected || [];
  const fmt = g => `${g.package}@${g.version} (${countBySeverity(g.findings.filter(f => f.decision !== "ignored"))}${g.kev ? ", exploited in the wild" : ""}) -> ${upgradeText(g)}`;
  const fail = groups.filter(g => g.decision === "fail"), warn = groups.filter(g => g.decision === "warn");
  if (fail.length) return `${fail.length} vulnerable package(s) introduced by this branch: ` + fail.slice(0, max).map(fmt).join("; ") + (fail.length > max ? `; +${fail.length - max}` : "");
  if (warn.length) {
    const old = warn.filter(g => !g.introduced).length;
    return `${warn.length} package(s) to review${old ? ` (${old} already in the base branch)` : ""}: ` + warn.slice(0, max).map(fmt).join("; ") + (warn.length > max ? `; +${warn.length - max}` : "");
  }
  if (report.notes.length && report.status !== "pass") return report.notes[0];
  return `${report.packages} packages checked (${report.sources.join(", ")})`;
}

/** Human-readable report: one block per package, advisories listed with --verbose. */
export function formatReport(report, { verbose = false } = {}) {
  const lines = [];
  lines.push(`Files: ${report.files.length ? report.files.join(", ") : "none"}`);
  lines.push(`Packages: ${report.packages}   Sources: ${report.sources.join(", ")}`);
  const tag = { fail: "FAIL", warn: "WARN", info: "INFO", ignored: "SKIP" };
  let hidden = 0;
  for (const g of report.packagesAffected || []) {
    if (!verbose && (g.decision === "info" || g.decision === "ignored")) { hidden++; continue; }
    lines.push("");
    lines.push(`  ${tag[g.decision]} ${g.package}@${g.version} [${g.ecosystem}] ${g.file}` +
      `${g.introduced ? "  (introduced by this branch)" : "  (already in the base branch)"}`);
    lines.push(`       ${countBySeverity(g.findings)}${g.kev ? "; EXPLOITED IN THE WILD (CISA KEV)" : ""}`);
    lines.push(`       -> ${upgradeText(g)}`);
    const shown = verbose ? g.findings : g.findings.filter(f => f.decision === "fail" || f.kev).slice(0, 5);
    for (const f of shown)
      lines.push(`       ${f.kev ? "KEV " : ""}${f.cves[0] || f.id} ${f.severity}${f.score != null ? " " + f.score : ""}: ${f.summary}` +
        `${f.ignoreReason ? `  [exception: ${f.ignoreReason}]` : ""}`);
    const more = g.findings.length - shown.length;
    if (more > 0) lines.push(`       ... ${more} more advisories (--verbose)`);
  }
  if (hidden) lines.push(`\n  (${hidden} low-severity or excepted package(s): --verbose to show)`);
  for (const e of report.errors) lines.push(`  WARN unreadable file: ${e}`);
  for (const n of report.notes) lines.push(`  NOTE ${n}`);
  if (report.sources.includes("NVD"))
    lines.push("\nThis product uses data from the NVD API but is not endorsed or certified by the NVD.");
  return lines.join("\n");
}

export const defaultCacheDir = gitDir =>
  process.env.REVIEW_HOOKS_DEPS_CACHE || path.join(gitDir, "review-hooks", "deps-cache");
