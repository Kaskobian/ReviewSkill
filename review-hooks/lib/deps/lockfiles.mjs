// review-hooks/lib/deps/lockfiles.mjs - Node.js 20+, no dependencies.
//
// Reads exact dependency versions from lock files and manifests.
// Every parser takes the file text and returns
//   [{ ecosystem, name, version }]
// with ecosystem names as used by OSV.dev. Unparseable or non-registry
// entries (git, path, workspace, ranges) are skipped, never guessed.

const SEMVERISH = /^\d+(\.\d+)*([.+-][0-9A-Za-z.+-]*)?$/;
const isVersion = v => typeof v === "string" && SEMVERISH.test(v);
const pep503 = n => n.toLowerCase().replace(/[-_.]+/g, "-");

// ── npm / pnpm / yarn ────────────────────────────────────────────────────────

export function parsePackageLock(text) {
  const j = JSON.parse(text);
  const out = [];
  if (j.packages) {                                   // lockfileVersion 2 and 3
    for (const [key, e] of Object.entries(j.packages)) {
      if (!key.includes("node_modules/") || e.link) continue;
      if (e.resolved && /^(git\+|git:|file:|https?:\/\/(?!registry\.))/.test(e.resolved)) continue;
      const name = e.name || key.slice(key.lastIndexOf("node_modules/") + 13);
      if (isVersion(e.version)) out.push({ ecosystem: "npm", name, version: e.version });
    }
    return out;
  }
  const walk = deps => {                              // lockfileVersion 1
    for (const [name, e] of Object.entries(deps || {})) {
      let { version } = e;
      const alias = /^npm:(.+)@([^@]+)$/.exec(version || "");
      if (alias) out.push({ ecosystem: "npm", name: alias[1], version: alias[2] });
      else if (isVersion(version)) out.push({ ecosystem: "npm", name, version });
      walk(e.dependencies);
    }
  };
  walk(j.dependencies);
  return out;
}

export function parsePnpmLock(text) {
  const out = [];
  let inPackages = false;
  for (const line of text.split(/\r?\n/)) {
    if (/^\S/.test(line)) { inPackages = /^packages:\s*$/.test(line); continue; }
    if (!inPackages) continue;
    const m = /^ {2}(['"]?)(.+?)\1:\s*$/.exec(line);
    if (!m) continue;
    const key = m[2].replace(/^\//, "").replace(/\(.*$/, "");
    // v5: name/1.2.3 or name/1.2.3_peer@x   v6+: name@1.2.3 or name@1.2.3(peer@x)
    const hit = /^((?:@[^/@]+\/)?[^/@]+)\/(\d[^_/]*)(?:_.*)?$/.exec(key) ||
                /^((?:@[^/@]+\/)?[^/@]+)@(\d[^@/]*)$/.exec(key);
    if (hit && isVersion(hit[2])) out.push({ ecosystem: "npm", name: hit[1], version: hit[2] });
  }
  return out;
}

export function parseYarnLock(text) {
  const out = [];
  let name = null;
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim() || line.startsWith("#")) continue;
    if (!/^\s/.test(line)) {                            // block header
      name = null;
      const spec = line.replace(/:\s*$/, "").split(",")[0].trim().replace(/^"|"$/g, "");
      const at = spec.lastIndexOf("@");
      if (at <= 0 || spec === "__metadata") continue;
      const range = spec.slice(at + 1);
      if (/^(workspace|link|file|portal|patch|exec|git|github):/.test(range) || /patch:/.test(spec)) continue;
      name = spec.slice(0, at);
      continue;
    }
    const v = /^ {2}version:?\s+"?([^"\s]+)"?\s*$/.exec(line);
    if (name && v && isVersion(v[1])) { out.push({ ecosystem: "npm", name, version: v[1] }); name = null; }
  }
  return out;
}

// ── NuGet ────────────────────────────────────────────────────────────────────

export function parseNugetLock(text) {
  const out = [];
  for (const framework of Object.values(JSON.parse(text).dependencies || {}))
    for (const [name, e] of Object.entries(framework))
      if (e.type !== "Project" && isVersion(e.resolved)) out.push({ ecosystem: "NuGet", name, version: e.resolved });
  return out;
}

const exactNuget = v => {
  if (!v) return null;
  const s = v.trim().replace(/^\[([^,\]]+)\]$/, "$1");   // [1.2.3] means exactly 1.2.3
  return isVersion(s) ? s : null;                        // ranges, $(Props), wildcards: skipped
};
const attr = (tag, a) => (new RegExp(`\\b${a}\\s*=\\s*"([^"]*)"`, "i").exec(tag) || [])[1];

/** .csproj / .fsproj / .vbproj / Directory.Packages.props / packages.config */
export function parseNugetProject(text) {
  const out = [];
  const re = /<(PackageReference|PackageVersion|package)\b([^>]*?)(?:\/>|>([\s\S]*?)<\/\1>)/gi;
  for (const m of text.matchAll(re)) {
    const [, tag, attrs, body = ""] = m;
    const name = tag.toLowerCase() === "package" ? attr(attrs, "id") : (attr(attrs, "Include") || attr(attrs, "Update"));
    const raw = tag.toLowerCase() === "package" ? attr(attrs, "version")
      : (attr(attrs, "Version") ?? (/<Version>([^<]*)<\/Version>/i.exec(body) || [])[1]);
    const version = exactNuget(raw);
    if (name && version) out.push({ ecosystem: "NuGet", name, version });
  }
  return out;
}

// ── Python ───────────────────────────────────────────────────────────────────

export function parseRequirements(text) {
  const out = [];
  const joined = text.replace(/\\\r?\n/g, " ");
  for (let line of joined.split(/\r?\n/)) {
    line = line.replace(/(^|\s)#.*$/, "").trim();
    if (!line || line.startsWith("-") || /:\/\//.test(line)) continue;
    const m = /^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*===?\s*([^\s;,]+)/.exec(line);
    if (m && isVersion(m[2])) out.push({ ecosystem: "PyPI", name: pep503(m[1]), version: m[2] });
  }
  return out;
}

/** [[package]] tables: poetry.lock, uv.lock, Cargo.lock */
function tomlPackages(text) {
  const blocks = text.split(/^\[\[package\]\]\s*$/m).slice(1);
  return blocks.map(b => {
    const body = b.split(/^\[\[(?!package\]\])/m)[0];
    const get = k => (new RegExp(`^${k}\\s*=\\s*"([^"]*)"`, "m").exec(body) || [])[1];
    return { name: get("name"), version: get("version"), body };
  });
}

export function parsePoetryOrUvLock(text) {
  return tomlPackages(text)
    .filter(p => p.name && isVersion(p.version))
    .filter(p => !/^\s*source\s*=\s*\{[^}]*\b(editable|virtual|path|directory|git)\s*=/m.test(p.body))
    .filter(p => !/^\s*type\s*=\s*"(directory|file|git|url)"/m.test(p.body))
    .map(p => ({ ecosystem: "PyPI", name: pep503(p.name), version: p.version }));
}

export function parsePipfileLock(text) {
  const j = JSON.parse(text);
  const out = [];
  for (const section of ["default", "develop"])
    for (const [name, e] of Object.entries(j[section] || {})) {
      const v = (e.version || "").replace(/^===?/, "");
      if (isVersion(v)) out.push({ ecosystem: "PyPI", name: pep503(name), version: v });
    }
  return out;
}

// ── Go, Rust, PHP, Ruby, Java ────────────────────────────────────────────────

export function parseGoMod(text) {
  const out = [];
  let inBlock = false;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.replace(/\/\/.*$/, "").trim();
    if (/^require\s*\($/.test(line)) { inBlock = true; continue; }
    if (inBlock && line === ")") { inBlock = false; continue; }
    const m = inBlock ? /^(\S+)\s+(v\S+)$/.exec(line) : /^require\s+(\S+)\s+(v\S+)$/.exec(line);
    if (m) out.push({ ecosystem: "Go", name: m[1], version: m[2] });
  }
  return out;
}

export function parseCargoLock(text) {
  return tomlPackages(text)
    .filter(p => p.name && isVersion(p.version) && /^\s*source\s*=\s*"registry\+/m.test(p.body))
    .map(p => ({ ecosystem: "crates.io", name: p.name, version: p.version }));
}

export function parseComposerLock(text) {
  const j = JSON.parse(text);
  return [...(j.packages || []), ...(j["packages-dev"] || [])]
    .map(p => ({ name: p.name, version: String(p.version || "").replace(/^v/, "") }))
    .filter(p => p.name && isVersion(p.version))
    .map(p => ({ ecosystem: "Packagist", ...p }));
}

export function parseGemfileLock(text) {
  const out = [];
  let inGem = false, inSpecs = false;
  for (const line of text.split(/\r?\n/)) {
    if (/^\S/.test(line)) { inGem = line.trim() === "GEM"; inSpecs = false; continue; }
    if (inGem && /^ {2}specs:\s*$/.test(line)) { inSpecs = true; continue; }
    if (!inSpecs) continue;
    const m = /^ {4}([^\s(]+) \(([^)]+)\)\s*$/.exec(line);
    if (!m) continue;
    const version = m[2].replace(/-(x86|x64|arm|aarch|universal|java|mingw|mswin|darwin|linux)[\w.-]*$/, "");
    if (isVersion(version)) out.push({ ecosystem: "RubyGems", name: m[1], version });
  }
  return out;
}

export function parseGradleLockfile(text) {
  const out = [];
  for (const line of text.split(/\r?\n/)) {
    const m = /^([^#\s:]+):([^:\s]+):([^=\s]+)=/.exec(line);
    if (m && isVersion(m[3])) out.push({ ecosystem: "Maven", name: `${m[1]}:${m[2]}`, version: m[3] });
  }
  return out;
}

// ── dispatch ─────────────────────────────────────────────────────────────────

const PARSERS = [
  [/(^|\/)package-lock\.json$|(^|\/)npm-shrinkwrap\.json$/, parsePackageLock],
  [/(^|\/)pnpm-lock\.yaml$/, parsePnpmLock],
  [/(^|\/)yarn\.lock$/, parseYarnLock],
  [/(^|\/)packages\.lock\.json$/, parseNugetLock],
  [/\.(cs|fs|vb)proj$|(^|\/)Directory\.Packages\.props$|(^|\/)packages\.config$/i, parseNugetProject],
  [/(^|\/)requirements[^/]*\.txt$|(^|\/)requirements\/[^/]+\.txt$/, parseRequirements],
  [/(^|\/)(poetry|uv)\.lock$/, parsePoetryOrUvLock],
  [/(^|\/)Pipfile\.lock$/, parsePipfileLock],
  [/(^|\/)go\.mod$/, parseGoMod],
  [/(^|\/)Cargo\.lock$/, parseCargoLock],
  [/(^|\/)composer\.lock$/, parseComposerLock],
  [/(^|\/)Gemfile\.lock$/, parseGemfileLock],
  [/(^|\/)gradle\.lockfile$/, parseGradleLockfile],
];
const VENDORED = /(^|\/)(node_modules|vendor|\.venv|venv|bin|obj|dist|build|target)\//;

export const isDependencyFile = file => !VENDORED.test(file) && PARSERS.some(([re]) => re.test(file));

/** Parse one file by name. Returns { packages, error } and never throws. */
export function parseDependencyFile(file, text) {
  const entry = PARSERS.find(([re]) => re.test(file));
  if (!entry) return { packages: [] };
  try {
    return { packages: entry[1](text.replace(/^\uFEFF/, "")).map(p => ({ ...p, file })) };
  } catch (e) {
    return { packages: [], error: `${file}: ${e.message}` };
  }
}

export const packageKey = p =>
  `${p.ecosystem}|${p.ecosystem === "NuGet" ? p.name.toLowerCase() : p.name}|${p.version}`;
