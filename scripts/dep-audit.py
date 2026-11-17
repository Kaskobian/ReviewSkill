#!/usr/bin/env python3
"""
Dependency Audit - known vulnerabilities in pinned dependencies (OWASP A03).

Reads lock files and manifests, asks OSV.dev which exact versions are
affected, marks CVEs that CISA lists as exploited in the wild (KEV), and can
fill missing CVSS scores from the NIST NVD. Deterministic: no AI, no
guessing - only versions that are pinned in a file are checked.

Why it exists: an agent asked "are our dependencies safe?" otherwise
answers from memory, which is out of date by definition. Run this, then
reason only about what it reports.

Usage:
    python dep-audit.py [PATH ...]           # scan directories/files (default: .)
    python dep-audit.py --json               # machine-readable
    python dep-audit.py --fail-on high       # exit 2 if any finding >= high (or in KEV)
    python dep-audit.py --nvd                # fill missing scores from NVD (slow without key)
    python dep-audit.py --offline            # parse only: list packages, no network

Environment:
    NVD_API_KEY   optional NVD key (50 requests / 30 s instead of 5). Never
                  commit it; set it in your shell or CI secret store.

Exit codes: 0 ok, 1 usage/network error, 2 --fail-on threshold reached.
Standard library only, Python 3.8+.

This product uses data from the NVD API but is not endorsed or certified by the NVD.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Iterable, List, Optional, Tuple

OSV = 'https://api.osv.dev/v1'
NVD = 'https://services.nvd.nist.gov/rest/json/cves/2.0'
KEV = 'https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json'
UA = {'User-Agent': 'code-review-skill dep-audit'}
SEVERITY = ['none', 'low', 'medium', 'high', 'critical']
VERSION = re.compile(r'^v?\d+(\.\d+)*([.+-][0-9A-Za-z.+-]*)?$')
SKIP_DIRS = {'node_modules', 'vendor', '.venv', 'venv', '.git', 'bin', 'obj', 'dist', 'build', 'target', '__pycache__'}

Package = Tuple[str, str, str, str]  # (ecosystem, name, version, file)


def _pep503(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name).lower()


def _ok(v) -> bool:
    return isinstance(v, str) and bool(VERSION.match(v))


# ── parsers (same rules as review-hooks/lib/deps/lockfiles.mjs) ──

def parse_package_lock(text: str) -> List[Tuple[str, str, str]]:
    j = json.loads(text)
    out = []
    if 'packages' in j:
        for key, e in j['packages'].items():
            if 'node_modules/' not in key or e.get('link'):
                continue
            res = e.get('resolved', '')
            if re.match(r'^(git\+|git:|file:|https?://(?!registry\.))', res):
                continue
            name = e.get('name') or key[key.rfind('node_modules/') + 13:]
            if _ok(e.get('version')):
                out.append(('npm', name, e['version']))
        return out

    def walk(deps):
        for name, e in (deps or {}).items():
            v = e.get('version', '')
            alias = re.match(r'^npm:(.+)@([^@]+)$', v)
            if alias:
                out.append(('npm', alias.group(1), alias.group(2)))
            elif _ok(v):
                out.append(('npm', name, v))
            walk(e.get('dependencies'))
    walk(j.get('dependencies'))
    return out


def parse_pnpm_lock(text: str):
    out, in_packages = [], False
    for line in text.splitlines():
        if re.match(r'^\S', line):
            in_packages = bool(re.match(r'^packages:\s*$', line))
            continue
        if not in_packages:
            continue
        m = re.match(r'''^ {2}(['"]?)(.+?)\1:\s*$''', line)
        if not m:
            continue
        key = re.sub(r'\(.*$', '', m.group(2).lstrip('/'))
        hit = (re.match(r'^((?:@[^/@]+/)?[^/@]+)/(\d[^_/]*)(?:_.*)?$', key)
               or re.match(r'^((?:@[^/@]+/)?[^/@]+)@(\d[^@/]*)$', key))
        if hit and _ok(hit.group(2)):
            out.append(('npm', hit.group(1), hit.group(2)))
    return out


def parse_yarn_lock(text: str):
    out, name = [], None
    for line in text.splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        if not line[0].isspace():
            name = None
            spec = re.sub(r':\s*$', '', line).split(',')[0].strip().strip('"')
            at = spec.rfind('@')
            if at <= 0 or spec == '__metadata':
                continue
            rng = spec[at + 1:]
            if re.match(r'^(workspace|link|file|portal|patch|exec|git|github):', rng) or 'patch:' in spec:
                continue
            name = spec[:at]
            continue
        m = re.match(r'''^ {2}version:?\s+"?([^"\s]+)"?\s*$''', line)
        if name and m and _ok(m.group(1)):
            out.append(('npm', name, m.group(1)))
            name = None
    return out


def parse_nuget_lock(text: str):
    out = []
    for fw in json.loads(text).get('dependencies', {}).values():
        for name, e in fw.items():
            if e.get('type') != 'Project' and _ok(e.get('resolved')):
                out.append(('NuGet', name, e['resolved']))
    return out


def parse_nuget_project(text: str):
    out = []
    pattern = re.compile(r'<(PackageReference|PackageVersion|package)\b([^>]*?)(?:/>|>([\s\S]*?)</\1>)', re.I)

    def attr(s, a):
        m = re.search(r'\b%s\s*=\s*"([^"]*)"' % a, s, re.I)
        return m.group(1) if m else None
    for m in pattern.finditer(text):
        tag, attrs, body = m.group(1).lower(), m.group(2), m.group(3) or ''
        if tag == 'package':
            name, raw = attr(attrs, 'id'), attr(attrs, 'version')
        else:
            name = attr(attrs, 'Include') or attr(attrs, 'Update')
            raw = attr(attrs, 'Version')
            if raw is None:
                vm = re.search(r'<Version>([^<]*)</Version>', body, re.I)
                raw = vm.group(1) if vm else None
        if raw:
            raw = re.sub(r'^\[([^,\]]+)\]$', r'\1', raw.strip())
        if name and _ok(raw):
            out.append(('NuGet', name, raw))
    return out


def parse_requirements(text: str):
    out = []
    for line in re.sub(r'\\\r?\n', ' ', text).splitlines():
        line = re.sub(r'(^|\s)#.*$', '', line).strip()
        if not line or line.startswith('-') or '://' in line:
            continue
        m = re.match(r'^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*===?\s*([^\s;,]+)', line)
        if m and _ok(m.group(2)):
            out.append(('PyPI', _pep503(m.group(1)), m.group(2)))
    return out


def _toml_packages(text: str):
    for block in re.split(r'^\[\[package\]\]\s*$', text, flags=re.M)[1:]:
        body = re.split(r'^\[\[(?!package\]\])', block, flags=re.M)[0]

        def get(k):
            m = re.search(r'^%s\s*=\s*"([^"]*)"' % k, body, re.M)
            return m.group(1) if m else None
        yield get('name'), get('version'), body


def parse_poetry_uv_lock(text: str):
    out = []
    for name, ver, body in _toml_packages(text):
        if not name or not _ok(ver):
            continue
        if re.search(r'^\s*source\s*=\s*\{[^}]*\b(editable|virtual|path|directory|git)\s*=', body, re.M):
            continue
        if re.search(r'^\s*type\s*=\s*"(directory|file|git|url)"', body, re.M):
            continue
        out.append(('PyPI', _pep503(name), ver))
    return out


def parse_pipfile_lock(text: str):
    j, out = json.loads(text), []
    for section in ('default', 'develop'):
        for name, e in (j.get(section) or {}).items():
            v = re.sub(r'^===?', '', e.get('version', ''))
            if _ok(v):
                out.append(('PyPI', _pep503(name), v))
    return out


def parse_go_mod(text: str):
    out, block = [], False
    for raw in text.splitlines():
        line = re.sub(r'//.*$', '', raw).strip()
        if re.match(r'^require\s*\($', line):
            block = True
            continue
        if block and line == ')':
            block = False
            continue
        m = re.match(r'^(\S+)\s+(v\S+)$', line) if block else re.match(r'^require\s+(\S+)\s+(v\S+)$', line)
        if m:
            out.append(('Go', m.group(1), m.group(2)))
    return out


def parse_cargo_lock(text: str):
    return [('crates.io', n, v) for n, v, body in _toml_packages(text)
            if n and _ok(v) and re.search(r'^\s*source\s*=\s*"registry\+', body, re.M)]


def parse_composer_lock(text: str):
    j = json.loads(text)
    out = []
    for p in (j.get('packages') or []) + (j.get('packages-dev') or []):
        v = str(p.get('version', '')).lstrip('v')
        if p.get('name') and _ok(v):
            out.append(('Packagist', p['name'], v))
    return out


def parse_gemfile_lock(text: str):
    out, in_gem, in_specs = [], False, False
    for line in text.splitlines():
        if line and not line[0].isspace():
            in_gem, in_specs = line.strip() == 'GEM', False
            continue
        if in_gem and re.match(r'^ {2}specs:\s*$', line):
            in_specs = True
            continue
        m = re.match(r'^ {4}([^\s(]+) \(([^)]+)\)\s*$', line) if in_specs else None
        if m:
            v = re.sub(r'-(x86|x64|arm|aarch|universal|java|mingw|mswin|darwin|linux)[\w.-]*$', '', m.group(2))
            if _ok(v):
                out.append(('RubyGems', m.group(1), v))
    return out


def parse_gradle_lockfile(text: str):
    out = []
    for line in text.splitlines():
        m = re.match(r'^([^#\s:]+):([^:\s]+):([^=\s]+)=', line)
        if m and _ok(m.group(3)):
            out.append(('Maven', '%s:%s' % (m.group(1), m.group(2)), m.group(3)))
    return out


PARSERS = [
    (r'(^|/)(package-lock|npm-shrinkwrap)\.json$', parse_package_lock),
    (r'(^|/)pnpm-lock\.yaml$', parse_pnpm_lock),
    (r'(^|/)yarn\.lock$', parse_yarn_lock),
    (r'(^|/)packages\.lock\.json$', parse_nuget_lock),
    (r'(?i)\.(cs|fs|vb)proj$|(^|/)Directory\.Packages\.props$|(^|/)packages\.config$', parse_nuget_project),
    (r'(^|/)requirements[^/]*\.txt$|(^|/)requirements/[^/]+\.txt$', parse_requirements),
    (r'(^|/)(poetry|uv)\.lock$', parse_poetry_uv_lock),
    (r'(^|/)Pipfile\.lock$', parse_pipfile_lock),
    (r'(^|/)go\.mod$', parse_go_mod),
    (r'(^|/)Cargo\.lock$', parse_cargo_lock),
    (r'(^|/)composer\.lock$', parse_composer_lock),
    (r'(^|/)Gemfile\.lock$', parse_gemfile_lock),
    (r'(^|/)gradle\.lockfile$', parse_gradle_lockfile),
]


def parser_for(path: str):
    p = path.replace('\\', '/')
    for pattern, fn in PARSERS:
        if re.search(pattern, p):
            return fn
    return None


def iter_dependency_files(paths: List[str]) -> Iterable[str]:
    for root in paths:
        if os.path.isfile(root):
            if parser_for(root):
                yield root
            continue
        for d, dirs, files in os.walk(root):
            dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
            for f in sorted(files):
                full = os.path.join(d, f)
                if parser_for(full):
                    yield full


def collect(paths: List[str]) -> Tuple[List[Package], List[str]]:
    pkgs, errors, seen = [], [], set()
    for f in iter_dependency_files(paths):
        try:
            parse = parser_for(f)
            if parse is None:
                continue
            with open(f, 'r', encoding='utf-8-sig', errors='replace') as h:
                found = parse(h.read())
        except (ValueError, OSError) as e:
            errors.append('%s: %s' % (f, e))
            continue
        for eco, name, ver in found:
            key = (eco, name.lower() if eco == 'NuGet' else name, ver)
            if key not in seen:
                seen.add(key)
                pkgs.append((eco, name, ver, f))
    return pkgs, errors


# ── network ──────────────────────────────────────────────────────────────────

def _request(url: str, body=None, headers=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    h = dict(UA, **(headers or {}))
    if data:
        h['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=h, method='POST' if data else 'GET')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def osv_query(pkgs: List[Package]) -> Dict[int, List[str]]:
    result = {}
    for start in range(0, len(pkgs), 500):
        chunk = pkgs[start:start + 500]
        res = _request(OSV + '/querybatch', {'queries': [
            {'package': {'name': n, 'ecosystem': e}, 'version': v} for e, n, v, _ in chunk]}, timeout=60)
        for i, r in enumerate(res.get('results', [])):
            result[start + i] = [v['id'] for v in r.get('vulns', [])]
    return result


# CVSS 3.x base score (FIRST specification)
def _round_up(x: float) -> float:
    i = round(x * 100000)
    return i / 100000.0 if i % 10000 == 0 else (i // 10000 + 1) / 10.0


def cvss3_score(vector: str) -> Optional[float]:
    if not re.match(r'^CVSS:3\.[01]/', vector or ''):
        return None
    m = dict(p.split(':', 1) for p in vector.split('/')[1:] if ':' in p)
    changed = m.get('S') == 'C'
    try:
        av = {'N': .85, 'A': .62, 'L': .55, 'P': .2}[m['AV']]
        ac = {'L': .77, 'H': .44}[m['AC']]
        pr = {'N': .85, 'L': .68 if changed else .62, 'H': .5 if changed else .27}[m['PR']]
        ui = {'N': .85, 'R': .62}[m['UI']]
        c, i_, a = ({'H': .56, 'L': .22, 'N': 0}[m[k]] for k in ('C', 'I', 'A'))
    except KeyError:
        return None
    iss = 1 - (1 - c) * (1 - i_) * (1 - a)
    impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15 if changed else 6.42 * iss
    if impact <= 0:
        return 0.0
    expl = 8.22 * av * ac * pr * ui
    return _round_up(min(1.08 * (impact + expl) if changed else impact + expl, 10))


def severity_of(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    return 'none' if score == 0 else 'low' if score < 4 else 'medium' if score < 7 else 'high' if score < 9 else 'critical'


def _vkey(v: str):
    core, _, pre = re.sub(r'^v', '', v).split('+')[0].partition('-')
    parts = [(0, int(x), '') if x.isdigit() else (1, 0, x) for x in core.split('.')]
    return parts, (1 if not pre else 0), pre


def _cmp(a: str, b: str) -> int:
    ka, kb = _vkey(a), _vkey(b)
    pa, pb = ka[0], kb[0]
    n = max(len(pa), len(pb))
    pa = pa + [(0, 0, '')] * (n - len(pa))
    pb = pb + [(0, 0, '')] * (n - len(pb))
    return (pa > pb) - (pa < pb) or (ka[1:] > kb[1:]) - (ka[1:] < kb[1:])


def fixed_for(rec: dict, eco: str, name: str, version: str) -> Optional[str]:
    norm = (lambda n: re.sub(r'[-_.]+', '-', n).lower()) if eco in ('NuGet', 'PyPI') else (lambda n: n)
    fixes = [e['fixed'] for a in rec.get('affected', [])
             if a.get('package', {}).get('ecosystem') == eco and norm(a['package'].get('name', '')) == norm(name)
             for r in a.get('ranges', []) for e in r.get('events', []) if 'fixed' in e]
    above = sorted((f for f in fixes if _cmp(f, version) > 0), key=lambda f: _vkey(f))
    return above[0] if above else None


def nvd_scores(cves: List[str], api_key: Optional[str], limit: int) -> Tuple[Dict[str, Tuple[float, str]], List[str]]:
    out, notes = {}, []
    gap = 0.7 if api_key else 6.0
    todo = list(dict.fromkeys(cves))
    if len(todo) > limit:
        notes.append('%d CVEs not looked up on NVD (limit %d per run)' % (len(todo) - limit, limit))
    for n, cve in enumerate(todo[:limit]):
        if n:
            time.sleep(gap)
        try:
            j = _request('%s?cveId=%s' % (NVD, cve), headers={'apiKey': api_key} if api_key else None)
        except (urllib.error.URLError, OSError, ValueError) as e:
            notes.append('NVD unavailable (%s): kept OSV scores' % e)
            break
        for item in j.get('vulnerabilities', []):
            metrics = item['cve'].get('metrics', {})
            for k in ('cvssMetricV40', 'cvssMetricV31', 'cvssMetricV30'):
                ms = metrics.get(k) or []
                m = next((x for x in ms if x.get('type') == 'Primary'), ms[0] if ms else None)
                if m:
                    d = m['cvssData']
                    out[cve] = (d['baseScore'], 'NVD CVSS ' + d.get('version', ''))
                    break
    return out, notes


def audit(pkgs: List[Package], use_nvd: bool, nvd_limit: int) -> Tuple[List[dict], List[str]]:
    notes = []
    refs = osv_query(pkgs)
    ids = sorted({v for ids in refs.values() for v in ids})
    with ThreadPoolExecutor(max_workers=8) as pool:   # one record per advisory; 8 in flight
        details: Dict[str, dict] = dict(zip(ids, pool.map(lambda v: _request('%s/vulns/%s' % (OSV, v)), ids)))
    try:
        kev = {v['cveID'] for v in _request(KEV, timeout=30).get('vulnerabilities', [])}
    except (urllib.error.URLError, OSError, ValueError) as e:
        kev = set()
        notes.append('CISA KEV unavailable (%s)' % e)
    findings = []
    for i, (eco, name, ver, f) in enumerate(pkgs):
        seen = set()
        for vid in refs.get(i, []):
            rec = details.get(vid) or {}
            if rec.get('withdrawn'):
                continue
            group = [rec.get('id', vid)] + rec.get('aliases', [])
            if any(g in seen for g in group):
                continue
            seen.update(group)
            cves = sorted({g for g in group if re.match(r'^CVE-\d{4}-\d+$', g)})
            v3 = next((s['score'] for s in rec.get('severity', []) if s.get('type') == 'CVSS_V3'), None)
            score = cvss3_score(v3) if v3 else None
            label = str(rec.get('database_specific', {}).get('severity', '')).lower().replace('moderate', 'medium')
            findings.append({
                'ecosystem': eco, 'package': name, 'version': ver, 'file': f, 'id': rec.get('id', vid),
                'cves': cves, 'summary': (rec.get('summary') or rec.get('details') or '').split('\n')[0][:160],
                'score': score, 'severity': severity_of(score) or (label if label in SEVERITY else 'unknown'),
                'source': 'OSV CVSS' if score is not None else ('advisory' if label in SEVERITY else None),
                'kev': any(c in kev for c in cves), 'fixed': fixed_for(rec, eco, name, ver),
                'cwes': rec.get('database_specific', {}).get('cwe_ids', []),
                'owasp': 'A03:2025 Software Supply Chain Failures',
                'url': 'https://osv.dev/vulnerability/' + rec.get('id', vid),
            })
    if use_nvd:
        gaps = [c for f in findings if f['score'] is None for c in f['cves']]
        scores, n = nvd_scores(gaps, os.environ.get('NVD_API_KEY'), nvd_limit)
        notes += n
        for f in findings:
            best = max((scores[c] for c in f['cves'] if c in scores), default=None, key=lambda s: s[0])
            if best and (f['score'] is None or best[0] > f['score']):
                f['score'], f['source'], f['severity'] = best[0], best[1], severity_of(best[0])
    rank = {s: i for i, s in enumerate(SEVERITY)}
    findings.sort(key=lambda f: (not f['kev'], -rank.get(f['severity'], -1), -(f['score'] or -1), f['package']))
    return findings, notes


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description='Known-vulnerability audit of pinned dependencies (OSV + CISA KEV + NVD)')
    ap.add_argument('paths', nargs='*', help='files or directories (default: .)')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--fail-on', choices=SEVERITY[1:], help='exit 2 if a finding is at/above this, or in KEV')
    ap.add_argument('--nvd', action='store_true', help='fill missing CVSS scores from the NIST NVD')
    ap.add_argument('--nvd-limit', type=int, default=10, help='max NVD lookups per run (default 10)')
    ap.add_argument('--offline', action='store_true', help='only list the pinned packages found')
    args = ap.parse_args(argv)
    reconfigure = getattr(sys.stdout, 'reconfigure', None)
    if callable(reconfigure):
        try:
            reconfigure(encoding='utf-8', errors='replace')
        except (ValueError, OSError):
            pass

    paths = args.paths or ['.']
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        print('Path not found: ' + ', '.join(missing), file=sys.stderr)
        return 1
    pkgs, errors = collect(paths)
    if args.offline:
        if args.json:
            print(json.dumps({'packages': [dict(zip(('ecosystem', 'name', 'version', 'file'), p)) for p in pkgs], 'errors': errors}, indent=2))
        else:
            for e, n, v, f in pkgs:
                print('%-10s %s@%s  (%s)' % (e, n, v, f))
            for e in errors:
                print('WARN unreadable: ' + e)
            print('%d pinned packages' % len(pkgs))
        return 0
    if not pkgs:
        print('No pinned dependencies found (lock files or exact versions).')
        return 0
    try:
        findings, notes = audit(pkgs, args.nvd, args.nvd_limit)
    except (urllib.error.URLError, OSError, ValueError) as e:
        print('OSV.dev unavailable: %s. Dependencies NOT checked.' % e, file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({'packages': len(pkgs), 'findings': findings, 'errors': errors, 'notes': notes,
                          'note': 'Known advisories for pinned versions. Check reachability before calling one exploitable.'},
                         indent=2, ensure_ascii=False))
    else:
        print('Dependency audit: %d pinned packages, %d advisories' % (len(pkgs), len(findings)))
        by_pkg: Dict[Tuple[str, str, str], List[dict]] = {}
        for f in findings:
            by_pkg.setdefault((f['ecosystem'], f['package'], f['version']), []).append(f)
        for (eco, name, ver), fs in by_pkg.items():
            fixes = [f['fixed'] for f in fs if f['fixed']]
            target = max(fixes, key=_vkey) if fixes else None
            kev = any(f['kev'] for f in fs)
            print('\n  %s@%s [%s] %s' % (name, ver, eco, fs[0]['file']))
            print('    %d advisories, worst %s%s -> %s' % (len(fs), fs[0]['severity'], ', EXPLOITED (CISA KEV)' if kev else '',
                                                        'upgrade to ' + target if target else 'no fixed version known'))
            for f in fs[:5]:
                print('    %s%s %s%s: %s' % ('KEV ' if f['kev'] else '', (f['cves'] or [f['id']])[0], f['severity'],
                                          ' %.1f' % f['score'] if f['score'] is not None else '', f['summary']))
            if len(fs) > 5:
                print('    ... %d more (--json)' % (len(fs) - 5))
        for e in errors:
            print('WARN unreadable: ' + e)
        for n in notes:
            print('NOTE ' + n)
        if args.nvd:
            print('\nThis product uses data from the NVD API but is not endorsed or certified by the NVD.')

    if args.fail_on:
        floor = SEVERITY.index(args.fail_on)
        if any(f['kev'] or (f['severity'] in SEVERITY and SEVERITY.index(f['severity']) >= floor) for f in findings):
            return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
