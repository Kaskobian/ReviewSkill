// review-hooks/lib/secrets.mjs - Node.js 20+, no dependencies.
//
// Deterministic credential check for the ADDED lines of a unified diff
// (output of `git diff` or `git log -p`). No AI involved.
//
// Hits report file, line and rule only - never the secret value - so they
// can be printed, logged and stored safely.

// High-confidence formats only, to keep false positives rare.
const CONTENT_RULES = [
  ["private-key", /-----BEGIN [A-Z ]*PRIVATE KEY-----/],
  ["aws-access-key", /\bAKIA[0-9A-Z]{16}\b/],
  ["github-token", /\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{22,}/],
  ["gitlab-token", /\bglpat-[A-Za-z0-9_-]{20,}/],
  ["slack-token", /\bxox[baprs]-[A-Za-z0-9-]{10,}/],
  ["stripe-live-key", /\b[sr]k_live_[0-9A-Za-z]{20,}/],
  ["google-api-key", /\bAIza[0-9A-Za-z_-]{35}\b/],
  ["azure-storage-key", /AccountKey=[A-Za-z0-9+/=]{40,}/],
  ["azure-shared-access-key", /SharedAccessKey=[A-Za-z0-9+/=]{20,}/],
  ["sas-signature", /[?&;]sig=[A-Za-z0-9%+/=]{30,}/],
  ["url-with-password", /\b[a-z][a-z0-9+.-]*:\/\/[^\s:/@'"]+:([^\s@/'"]{6,})@/i, 1],
  // Connection-string style "...;Password=xyz;" (no spaces around "=", so
  // code such as `password = forms.CharField(...)` does not match).
  ["connection-string-password", /(?:^|[;"'])\s*(?:Password|Pwd)=([^;"'\s]{6,})/i, 1],
  ["generic-secret-value",
    /["']?(?:api[_-]?key|apikey|client[_-]?secret|secret[_-]?key|access[_-]?token|auth[_-]?token|private[_-]?key)["']?\s*[:=]\s*["']([A-Za-z0-9_\-+/=.]{24,})["']/i, 1],
];

// Files that should never be committed, whatever they contain.
const FILE_RULES = [
  ["env-file", /(?:^|\/)\.env(?:\.(?!example$|sample$|template$|dist$)[^/]+)?$/i],
  ["azure-functions-local-settings", /(?:^|\/)local\.settings\.json$/i],
  ["key-material", /\.(?:pfx|p12|pem|key|jks|keystore)$/i],
  ["ssh-private-key", /(?:^|\/)id_(?:rsa|dsa|ecdsa|ed25519)$/],
];

const PLACEHOLDER = /^(?:changeme|change_me|example|sample|dummy|placeholder|password|secret|test|xxx+|\*+|redacted|none|null)$|^[<{$%]|your[_-]|\$\{|\{\{|process\.env|os\.environ|getenv|\(/i;

const looksRandom = v => /[0-9]/.test(v) && /[A-Za-z]/.test(v) && new Set(v).size >= 10;

/**
 * @param {string} diff unified diff text
 * @param {{ allow?: string[] }} [opts] path globs to skip (e.g. test fixtures)
 * @returns {{file: string, line: number, rule: string}[]}
 */
export function scanDiffForSecrets(diff, opts = {}) {
  const allow = (opts.allow || []).map(globToRegExp);
  const skip = f => allow.some(re => re.test(f));
  const hits = [];
  const seen = new Set();
  let file = null, line = 0, inHunk = false;
  for (const raw of diff.split("\n")) {
    if (raw.startsWith("diff --git ")) { file = null; inHunk = false; continue; }
    if (raw.startsWith("+++ ")) {
      const target = raw.slice(4).trim();
      file = target === "/dev/null" ? null : target.replace(/^b\//, "");
      if (file && skip(file)) file = null;
      if (file && !seen.has(file)) {
        seen.add(file);
        for (const [rule, re] of FILE_RULES) if (re.test(file)) hits.push({ file, line: 0, rule });
      }
      continue;
    }
    const hunk = /^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(raw);
    if (hunk) { line = Number(hunk[1]); inHunk = true; continue; }
    if (!inHunk || file === null) continue;
    if (raw.startsWith("+")) {
      const text = raw.slice(1);
      for (const [rule, re, group] of CONTENT_RULES) {
        const m = re.exec(text);
        if (!m) continue;
        if (/EXAMPLE/.test(m[0])) continue; // vendor documentation keys, e.g. AKIA...EXAMPLE
        if (group) {
          const value = m[group];
          if (PLACEHOLDER.test(value)) continue;
          if (rule === "generic-secret-value" && !looksRandom(value)) continue;
        }
        hits.push({ file, line, rule });
        break;
      }
      line += 1;
    } else if (!raw.startsWith("-") && !raw.startsWith("\\")) {
      line += 1;
    }
  }
  return hits;
}

export function describeSecretHits(hits, max = 5) {
  const parts = hits.slice(0, max).map(h => `${h.file}${h.line ? ":" + h.line : ""} (${h.rule})`);
  if (hits.length > max) parts.push(`+${hits.length - max} more`);
  return parts.join(", ");
}

// Minimal glob: ** = any path, * = any segment chars, ? = one char.
export function globToRegExp(glob) {
  let re = "";
  for (let i = 0; i < glob.length; i++) {
    const c = glob[i];
    if (c === "*" && glob[i + 1] === "*") { re += ".*"; i++; if (glob[i + 1] === "/") i++; }
    else if (c === "*") re += "[^/]*";
    else if (c === "?") re += "[^/]";
    else re += c.replace(/[.+^${}()|[\]\\]/g, "\\$&");
  }
  return new RegExp("^" + re + "$");
}
