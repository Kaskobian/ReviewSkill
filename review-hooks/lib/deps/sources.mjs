// review-hooks/lib/deps/sources.mjs - Node.js 20+, no dependencies.
//
// Vulnerability data from three public sources, with a local cache:
//   OSV.dev   which exact package versions are affected, and the fix version
//   NVD (NIST) CVSS score and CWE for each CVE        (optional key: NVD_API_KEY)
//   CISA KEV  whether a CVE is known to be exploited in the wild
//
// All network access goes through `http` (the global fetch by default), so
// tests can run fully offline. Nothing here decides pass/fail.
//
// This product uses data from the NVD API but is not endorsed or certified by the NVD.

import fs from "node:fs";
import path from "node:path";

// Overridable for corporate mirrors and offline tests.
const OSV = process.env.REVIEW_HOOKS_OSV_URL || "https://api.osv.dev/v1";
const NVD = process.env.REVIEW_HOOKS_NVD_URL || "https://services.nvd.nist.gov/rest/json/cves/2.0";
const KEV = process.env.REVIEW_HOOKS_KEV_URL || "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json";
const OSV_ECOSYSTEMS = new Set(["npm", "NuGet", "PyPI", "Go", "crates.io", "Packagist", "RubyGems", "Maven"]);
const DAY = 24 * 3600 * 1000;

export const SEVERITY_ORDER = ["none", "low", "medium", "high", "critical"];
export const severityRank = s => Math.max(0, SEVERITY_ORDER.indexOf(String(s || "").toLowerCase()));

const sleep = ms => new Promise(r => setTimeout(r, ms));

// ── cache ────────────────────────────────────────────────────────────────────

export class Cache {
  constructor(dir) { this.dir = dir; if (dir) fs.mkdirSync(dir, { recursive: true }); }
  #file(ns, key) { return path.join(this.dir, ns, encodeURIComponent(key).slice(0, 180) + ".json"); }
  get(ns, key, maxAgeMs) {
    if (!this.dir) return undefined;
    try {
      const f = this.#file(ns, key);
      const age = Date.now() - fs.statSync(f).mtimeMs;
      if (maxAgeMs !== undefined && age > maxAgeMs) return undefined;
      return JSON.parse(fs.readFileSync(f, "utf8"));
    } catch { return undefined; }
  }
  set(ns, key, value) {
    if (!this.dir) return;
    const f = this.#file(ns, key);
    fs.mkdirSync(path.dirname(f), { recursive: true });
    const tmp = `${f}.${process.pid}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(value));
    fs.renameSync(tmp, f);
  }
}

async function getJson(http, url, { method = "GET", body, headers = {}, timeoutMs = 20000 } = {}) {
  const res = await http(url, {
    method, headers: { "User-Agent": "review-hooks", ...(body ? { "Content-Type": "application/json" } : {}), ...headers },
    body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) {
    const err = new Error(`HTTP ${res.status}${res.headers?.get?.("message") ? ": " + res.headers.get("message") : ""}`);
    err.status = res.status;
    err.nvdMessage = res.headers?.get?.("message") || "";
    throw err;
  }
  return res.json();
}

async function pool(items, size, fn) {
  const out = new Array(items.length);
  let i = 0;
  await Promise.all(Array.from({ length: Math.min(size, items.length) }, async () => {
    while (i < items.length) { const n = i++; out[n] = await fn(items[n], n); }
  }));
  return out;
}

// ── versions ─────────────────────────────────────────────────────────────────

/** Numeric-aware compare: 1.10.0 > 1.9.0, 1.0.0 > 1.0.0-rc1. Good enough to pick a fix version. */
export function compareVersions(a, b) {
  const split = v => String(v).replace(/^v/, "").split(/[+]/)[0].split(/[-]/);
  const [ca, pa] = [split(a)[0], split(a).slice(1).join("-")];
  const [cb, pb] = [split(b)[0], split(b).slice(1).join("-")];
  const na = ca.split("."), nb = cb.split(".");
  for (let i = 0; i < Math.max(na.length, nb.length); i++) {
    const x = na[i] ?? "0", y = nb[i] ?? "0";
    const d = /^\d+$/.test(x) && /^\d+$/.test(y) ? Number(x) - Number(y) : x.localeCompare(y);
    if (d) return Math.sign(d);
  }
  if (pa && !pb) return -1;
  if (!pa && pb) return 1;
  return Math.sign(pa.localeCompare(pb, undefined, { numeric: true }));
}

/** Smallest "fixed" version above `current` for this package in an OSV record. */
export function fixedVersion(osv, pkg) {
  const norm = n => pkg.ecosystem === "NuGet" || pkg.ecosystem === "PyPI" ? n.toLowerCase().replace(/[-_.]+/g, "-") : n;
  const fixes = [];
  for (const a of osv.affected || []) {
    if (a.package?.ecosystem !== pkg.ecosystem || norm(a.package?.name || "") !== norm(pkg.name)) continue;
    for (const r of a.ranges || []) for (const e of r.events || []) if (e.fixed) fixes.push(e.fixed);
  }
  const above = fixes.filter(f => compareVersions(f, pkg.version) > 0).sort(compareVersions);
  return above[0] || null;
}

// ── CVSS 3.x base score (FIRST spec), used when NVD has no data ─────────────

const roundUp = x => { const i = Math.round(x * 100000); return i % 10000 === 0 ? i / 100000 : (Math.floor(i / 10000) + 1) / 10; };

export function cvss3Score(vector) {
  const m = Object.fromEntries(String(vector || "").split("/").slice(1).map(p => p.split(":")));
  if (!/^CVSS:3\.[01]\//.test(vector || "") || !m.AV || !m.S) return null;
  const AV = { N: 0.85, A: 0.62, L: 0.55, P: 0.2 }[m.AV], AC = { L: 0.77, H: 0.44 }[m.AC];
  const changed = m.S === "C";
  const PR = { N: 0.85, L: changed ? 0.68 : 0.62, H: changed ? 0.5 : 0.27 }[m.PR], UI = { N: 0.85, R: 0.62 }[m.UI];
  const cia = k => ({ H: 0.56, L: 0.22, N: 0 })[m[k]];
  if ([AV, AC, PR, UI, cia("C"), cia("I"), cia("A")].some(v => v === undefined)) return null;
  const iss = 1 - (1 - cia("C")) * (1 - cia("I")) * (1 - cia("A"));
  const impact = changed ? 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15 : 6.42 * iss;
  const expl = 8.22 * AV * AC * PR * UI;
  if (impact <= 0) return 0;
  return roundUp(Math.min(changed ? 1.08 * (impact + expl) : impact + expl, 10));
}

export const scoreToSeverity = s =>
  s == null ? null : s === 0 ? "none" : s < 4 ? "low" : s < 7 ? "medium" : s < 9 ? "high" : "critical";

/** Severity from an OSV record alone: CVSS 3 vector, else the advisory's label. */
export function osvSeverity(rec) {
  const v3 = (rec.severity || []).find(s => s.type === "CVSS_V3");
  const score = v3 ? cvss3Score(v3.score) : null;
  if (score != null) return { score, severity: scoreToSeverity(score), source: "OSV CVSS" };
  const label = String(rec.database_specific?.severity || "").toLowerCase().replace("moderate", "medium");
  return SEVERITY_ORDER.includes(label) ? { score: null, severity: label, source: "advisory" } : { score: null, severity: null, source: null };
}

// ── OSV ──────────────────────────────────────────────────────────────────────

/**
 * @returns {Promise<Map<string, {id: string, modified: string}[]>>} packageKey -> vuln refs
 */
export async function osvQuery(packages, { http = fetch, cache, keyOf }) {
  const result = new Map();
  const todo = [];
  for (const p of packages) {
    if (!OSV_ECOSYSTEMS.has(p.ecosystem)) continue;
    const hit = cache?.get("osv-query", keyOf(p), 12 * 3600 * 1000);
    if (hit) result.set(keyOf(p), hit); else todo.push(p);
  }
  for (let i = 0; i < todo.length; i += 500) {
    const chunk = todo.slice(i, i + 500);
    const res = await getJson(http, `${OSV}/querybatch`, {
      method: "POST", timeoutMs: 60000,
      body: { queries: chunk.map(p => ({ package: { name: p.name, ecosystem: p.ecosystem }, version: p.version })) },
    });
    for (const [n, r] of (res.results || []).entries()) {
      let vulns = r.vulns || [];
      let token = r.next_page_token;
      while (token) {                                  // rare: very many advisories for one version
        const p = chunk[n];
        const more = await getJson(http, `${OSV}/query`, {
          method: "POST", body: { package: { name: p.name, ecosystem: p.ecosystem }, version: p.version, page_token: token },
        });
        vulns = vulns.concat(more.vulns || []);
        token = more.next_page_token;
      }
      const refs = vulns.map(v => ({ id: v.id, modified: v.modified }));
      result.set(keyOf(chunk[n]), refs);
      cache?.set("osv-query", keyOf(chunk[n]), refs);
    }
  }
  return result;
}

export async function osvDetails(refs, { http = fetch, cache }) {
  const unique = [...new Map(refs.map(r => [r.id, r])).values()];
  const out = new Map();
  await pool(unique, 8, async ref => {
    const key = `${ref.id}@${ref.modified || ""}`;
    let rec = cache?.get("osv-vuln", key);
    if (!rec) { rec = await getJson(http, `${OSV}/vulns/${encodeURIComponent(ref.id)}`); cache?.set("osv-vuln", key, rec); }
    out.set(ref.id, rec);
  });
  return out;
}

// ── CISA KEV ─────────────────────────────────────────────────────────────────

/** @returns {Promise<{set: Set<string>, stale: boolean, error?: string}>} */
export async function loadKev({ http = fetch, cache }) {
  const fresh = cache?.get("kev", "catalog", DAY);
  if (fresh) return { set: new Set(fresh), stale: false };
  try {
    const j = await getJson(http, KEV, { timeoutMs: 30000 });
    const ids = (j.vulnerabilities || []).map(v => v.cveID);
    cache?.set("kev", "catalog", ids);
    return { set: new Set(ids), stale: false };
  } catch (e) {
    const old = cache?.get("kev", "catalog");
    return { set: new Set(old || []), stale: true, error: e.message, missing: !old };
  }
}

// ── NVD ──────────────────────────────────────────────────────────────────────

export function nvdSummary(cve) {
  const metrics = cve.metrics || {};
  const pick = (list = []) => list.find(m => m.type === "Primary") || list[0];
  const m = pick(metrics.cvssMetricV40) || pick(metrics.cvssMetricV31) || pick(metrics.cvssMetricV30);
  const v2 = !m && pick(metrics.cvssMetricV2);
  const data = (m || v2)?.cvssData || {};
  return {
    id: cve.id,
    status: cve.vulnStatus,
    score: data.baseScore ?? null,
    severity: String(data.baseSeverity || v2?.baseSeverity || "").toLowerCase() || null,
    cvssVersion: data.version || null,
    cwes: [...new Set((cve.weaknesses || []).flatMap(w => w.description.map(d => d.value)).filter(v => /^CWE-\d+$/.test(v)))],
    kev: cve.cisaExploitAdd ? { added: cve.cisaExploitAdd, due: cve.cisaActionDue } : null,
  };
}

/**
 * Look up CVEs one at a time, as the NVD asks. Without a key the public limit
 * is 5 requests per 30 s, so lookups are spaced 6 s apart and capped per run;
 * with a key they are spaced ~0.7 s. Results are cached for a week.
 */
export async function nvdLookup(cveIds, { http = fetch, cache, apiKey, maxLookups = 25, now = () => Date.now(), wait = sleep }) {
  const out = new Map();
  const notes = [];
  let key = apiKey && /^[0-9a-f-]{36}$/i.test(apiKey) ? apiKey : null;
  if (apiKey && !key) notes.push("NVD_API_KEY is not a valid key format: ignored");
  const todo = [];
  for (const id of [...new Set(cveIds)]) {
    const hit = cache?.get("nvd", id, 7 * DAY);
    if (hit !== undefined) out.set(id, hit); else todo.push(id);
  }
  const limit = Math.min(todo.length, maxLookups);
  if (todo.length > limit) notes.push(`${todo.length - limit} CVE(s) not looked up on NVD this run (limit ${maxLookups}): later runs will fill them in`);
  let last = null;
  for (let n = 0; n < limit; n++) {
    const id = todo[n];
    const gap = key ? 700 : 6000;
    if (last !== null) { const delay = last + gap - now(); if (delay > 0) await wait(delay); }
    last = now();
    try {
      const j = await getJson(http, `${NVD}?cveId=${encodeURIComponent(id)}`, { headers: key ? { apiKey: key } : {} });
      const cve = j.vulnerabilities?.[0]?.cve;
      const summary = cve ? nvdSummary(cve) : null;
      out.set(id, summary);
      cache?.set("nvd", id, summary);
    } catch (e) {
      if (key && e.status === 404 && /apikey/i.test(e.nvdMessage)) {
        notes.push("NVD rejected NVD_API_KEY (Invalid apiKey): continuing without a key");
        key = null;
        n--;                                          // retry this CVE without the key
        continue;
      }
      notes.push(`NVD unreachable (${e.message}): using OSV CVSS scores where available`);
      break;                                          // don't hammer a failing service
    }
  }
  return { byId: out, notes };
}
