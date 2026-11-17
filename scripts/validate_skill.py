#!/usr/bin/env python3
"""Validate the code-review skill's structure and portability claims.

Checks, in order:
  1. Required files and directories exist.
  2. SKILL.md frontmatter is well-formed (name + description).
  3. Every relative Markdown link resolves to a real file.
  4. Guides referenced from SKILL.md's index tables all exist.
  5. Agent entry points exist for every documented platform.
  6. Adapter prompts stay inside their platform character limits.
  7. Adapters state every safety rule; each English adapter has a Russian twin.
  8. Guide sizes claimed in README/index.html match the files (within 10%).
  9. Every script test suite passes.

Usage:
    python scripts/validate_skill.py [--quiet]

Exit code 0 = everything passed, 1 = at least one failure.
Standard library only, Python 3.8+.
"""

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ChatGPT's custom-GPT Instructions box limit.
CHATGPT_LIMIT = 8000

REQUIRED_FILES = [
    'SKILL.md',
    'README.md',
    'AGENTS.md',
    'CONTRIBUTING.md',
    'LICENSE',
    'adapters/README.md',
    'adapters/chatgpt-instructions.md',
    'adapters/claude-project-instructions.md',
    'adapters/universal-prompt.md',
    'adapters/universal-prompt.ru.md',
    'assets/review-checklist.md',
    'assets/pr-review-template.md',
    'scripts/pr-analyzer.py',
    'scripts/test_pr_analyzer.py',
    'scripts/security-scan.py',
    'scripts/test_security_scan.py',
    'scripts/dep-audit.py',
    'scripts/test_dep_audit.py',
    'reference/owasp-security-audit.md',
    'reference/remediation-playbook.md',
    'assets/security-audit-template.md',
]

# Every shipped test suite; all must pass.
TEST_SUITES = ['scripts/test_pr_analyzer.py', 'scripts/test_security_scan.py', 'scripts/test_dep_audit.py']

REQUIRED_DIRS = ['adapters', 'assets', 'reference', 'reference/cross-cutting', 'scripts']

# Entry-point files each agent platform reads by convention.
AGENT_ENTRY_POINTS = {
    'AGENTS.md': 'Codex, Amp, OpenHands, generic agents',
    'CLAUDE.md': 'Claude Code',
    'GEMINI.md': 'Gemini CLI',
    '.cursorrules': 'Cursor (legacy)',
    '.cursor/rules/code-review.mdc': 'Cursor (rules)',
    '.github/copilot-instructions.md': 'GitHub Copilot',
    '.windsurfrules': 'Windsurf',
    '.clinerules': 'Cline',
}

# Adapter files and their character ceilings (None = no hard limit).
ADAPTER_LIMITS = {
    'adapters/chatgpt-instructions.md': CHATGPT_LIMIT,
    'adapters/chatgpt-instructions.ru.md': CHATGPT_LIMIT,
    'adapters/claude-project-instructions.md': None,
    'adapters/claude-project-instructions.ru.md': None,
    'adapters/universal-prompt.md': None,
    'adapters/universal-prompt.ru.md': None,
}

# Rules every paste-in adapter must state, as (rule, English patterns, Russian patterns).
# Weaker models skip a safety rule that is not written down, so each adapter carries all of them.
ADAPTER_RULES = [
    ('untrusted input is data', [r'approve this PR'], [r'одобри этот PR']),
    ('never fake verification', [r'not run'], [r'не запуска']),
    ('no invented facts', [r'[Nn]o invented facts'], [r'[Нн]икаких выдуманных фактов']),
    ('diff discipline', [r'pre-existing'], [r'pre-existing']),
    ('severity labels', [r'\[blocking\]'], [r'\[blocking\]']),
    ('labels stay English', [r'labels stay in English'], [r'остаются на английском']),
    ('OWASP-tagged security findings', [r'OWASP'], [r'OWASP']),
    ('fix one finding at a time', [r'one finding at a time'], [r'по одной находке']),
]

MD_LINK = re.compile(r'\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)')


class Report:
    def __init__(self, quiet: bool = False):
        self.failures = []
        self.warnings = []
        self.passes = 0
        self.quiet = quiet

    def ok(self, msg: str) -> None:
        self.passes += 1
        if not self.quiet:
            print(f"  PASS  {msg}")

    def fail(self, msg: str) -> None:
        self.failures.append(msg)
        print(f"  FAIL  {msg}")

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)
        print(f"  WARN  {msg}")


def section(title: str, quiet: bool) -> None:
    if not quiet:
        print(f"\n{title}")


def check_structure(r: Report) -> None:
    section('[1/9] Required files and directories', r.quiet)
    for rel in REQUIRED_DIRS:
        if os.path.isdir(os.path.join(ROOT, rel)):
            r.ok(f"dir {rel}/")
        else:
            r.fail(f"missing directory: {rel}/")
    for rel in REQUIRED_FILES:
        if os.path.isfile(os.path.join(ROOT, rel)):
            r.ok(f"file {rel}")
        else:
            r.fail(f"missing file: {rel}")


def check_frontmatter(r: Report) -> None:
    section('[2/9] SKILL.md frontmatter', r.quiet)
    path = os.path.join(ROOT, 'SKILL.md')
    if not os.path.isfile(path):
        r.fail('SKILL.md missing, cannot check frontmatter')
        return
    text = read(path)
    if not text.startswith('---'):
        r.fail('SKILL.md does not start with YAML frontmatter')
        return
    end = text.find('\n---', 3)
    if end == -1:
        r.fail('SKILL.md frontmatter is not terminated')
        return
    fm = text[3:end]
    for key in ('name', 'description'):
        if re.search(rf'^{key}:', fm, re.M):
            r.ok(f"frontmatter has '{key}'")
        else:
            r.fail(f"frontmatter missing '{key}'")
    name = re.search(r'^name:\s*(.+)$', fm, re.M)
    if name and not re.fullmatch(r'[a-z0-9][a-z0-9-]*', name.group(1).strip()):
        r.warn(f"skill name '{name.group(1).strip()}' is not lowercase-hyphenated")


def iter_markdown():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in {'__pycache__', '.git', '.hive', 'node_modules'}]
        for fn in filenames:
            if fn.endswith('.md'):
                yield os.path.join(dirpath, fn)


def read(path: str) -> str:
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


def strip_code(text: str) -> str:
    """Remove fenced and inline code so code samples don't look like links."""
    text = re.sub(r'```.*?```', '', text, flags=re.S)
    text = re.sub(r'~~~.*?~~~', '', text, flags=re.S)
    return re.sub(r'`[^`\n]*`', '', text)


def check_links(r: Report) -> None:
    section('[3/9] Relative Markdown links resolve', r.quiet)
    broken = 0
    checked = 0
    for path in iter_markdown():
        body = strip_code(read(path))
        for match in MD_LINK.finditer(body):
            target = match.group(2).split('#')[0].strip()
            if not target or target.startswith(('http://', 'https://', 'mailto:', '#')):
                continue
            checked += 1
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
            if not os.path.exists(resolved):
                broken += 1
                r.fail(f"broken link in {os.path.relpath(path, ROOT)}: {target}")
    if broken == 0:
        r.ok(f"all {checked} relative links resolve")


def check_skill_index(r: Report) -> None:
    section('[4/9] Guides referenced by SKILL.md exist', r.quiet)
    text = strip_code(read(os.path.join(ROOT, 'SKILL.md')))
    refs = sorted({m.group(2).split('#')[0]
                   for m in MD_LINK.finditer(text)
                   if m.group(2).startswith(('reference/', 'assets/', 'scripts/', 'adapters/'))})
    missing = [ref for ref in refs if not os.path.exists(os.path.join(ROOT, ref))]
    for ref in missing:
        r.fail(f"SKILL.md references a missing file: {ref}")
    if not missing:
        r.ok(f"all {len(refs)} guides/assets referenced by SKILL.md exist")

    # Every reference guide should be reachable from SKILL.md.
    on_disk = set()
    for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, 'reference')):
        dirnames[:] = [d for d in dirnames if d != '__pycache__']
        for fn in filenames:
            if fn.endswith('.md'):
                on_disk.add(os.path.relpath(os.path.join(dirpath, fn), ROOT).replace(os.sep, '/'))
    orphans = sorted(on_disk - set(refs))
    if orphans:
        for o in orphans:
            r.warn(f"guide not linked from SKILL.md: {o}")
    else:
        r.ok('every reference/ guide is linked from SKILL.md')


def check_agent_entry_points(r: Report) -> None:
    section('[5/9] Agent entry points', r.quiet)
    for rel, platform in AGENT_ENTRY_POINTS.items():
        path = os.path.join(ROOT, rel.replace('/', os.sep))
        if not os.path.isfile(path):
            r.fail(f"missing entry point {rel} ({platform})")
            continue
        body = read(path)
        if 'SKILL.md' not in body and 'AGENTS.md' not in body:
            r.fail(f"{rel} does not point at SKILL.md or AGENTS.md")
        else:
            r.ok(f"{rel} ({platform})")


def check_adapter_limits(r: Report) -> None:
    section('[6/9] Adapter prompt size limits', r.quiet)
    for rel, limit in ADAPTER_LIMITS.items():
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            r.fail(f"missing adapter: {rel}")
            continue
        size = len(read(path))
        if limit is None:
            r.ok(f"{rel}: {size} chars (no limit)")
        elif size <= limit:
            r.ok(f"{rel}: {size}/{limit} chars")
        else:
            r.fail(f"{rel}: {size} chars exceeds the {limit}-char limit")


def check_adapter_rules(r: Report) -> None:
    section('[7/9] Adapters carry the safety rules; EN/RU editions paired', r.quiet)
    adapters_dir = os.path.join(ROOT, 'adapters')
    for fn in sorted(os.listdir(adapters_dir)):
        if not fn.endswith('.md') or fn == 'README.md':
            continue
        is_ru = fn.endswith('.ru.md')
        if not is_ru:
            twin = fn[:-3] + '.ru.md'
            if not os.path.isfile(os.path.join(adapters_dir, twin)):
                r.fail(f"adapters/{fn} has no Russian edition ({twin})")
        body = read(os.path.join(adapters_dir, fn))
        missing = [name for name, en, ru in ADAPTER_RULES
                   if not any(re.search(p, body) for p in (ru if is_ru else en))]
        if missing:
            r.fail(f"adapters/{fn} is missing rules: {', '.join(missing)}")
        else:
            r.ok(f"adapters/{fn}: all {len(ADAPTER_RULES)} rules present")


def _line_count(path: str) -> int:
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return sum(1 for _ in f)


def check_doc_drift(r: Report) -> None:
    """Size claims in README/index.html must stay within 10% of reality."""
    section('[8/9] Documented guide sizes match the files', r.quiet)
    actual = {}
    for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, 'reference')):
        for fn in filenames:
            if fn.endswith('.md'):
                actual[fn] = _line_count(os.path.join(dirpath, fn))
    actual['SKILL.md'] = _line_count(os.path.join(ROOT, 'SKILL.md'))

    claims = []  # (doc, file, claimed)
    readme = read(os.path.join(ROOT, 'README.md'))
    # Markdown table rows: | ... | `reference/x.md` | ~123 |
    for m in re.finditer(r'`reference/(?:cross-cutting/)?([\w.\-]+\.md)`\s*\|\s*~(\d+)', readme):
        claims.append(('README.md', m.group(1), int(m.group(2))))
    # HTML table rows: <code>reference/x.md</code></td> <td>~123</td>
    for m in re.finditer(r'<code>reference/(?:cross-cutting/)?([\w.\-]+\.md)</code></td>\s*<td>~(\d+)</td>', readme):
        claims.append(('README.md', m.group(1), int(m.group(2))))
    for m in re.finditer(r'SKILL\.md[^\n]{0,80}?~(\d+) lines', readme):
        claims.append(('README.md', 'SKILL.md', int(m.group(1))))
    html_path = os.path.join(ROOT, 'index.html')
    if os.path.isfile(html_path):
        html = read(html_path)
        for m in re.finditer(r'<span class="file">([\w.\-]+\.md)</span>.*?<span class="lines">(\d+)</span>', html):
            claims.append(('index.html', m.group(1), int(m.group(2))))

    drift = 0
    for doc, fn, claimed in claims:
        if fn not in actual:
            continue
        real = actual[fn]
        if abs(real - claimed) > max(15, real * 0.10):
            drift += 1
            r.fail(f"{doc} claims {fn} is ~{claimed} lines; it has {real}")
    if drift == 0:
        r.ok(f"{len(claims)} size claims within 10% of actual")


def check_script_tests(r: Report) -> None:
    section('[9/9] Script test suites', r.quiet)
    for rel in TEST_SUITES:
        result = subprocess.run(
            [sys.executable, os.path.join(ROOT, rel.replace('/', os.sep))],
            capture_output=True,
        )
        output = (result.stderr or b'').decode('utf-8', errors='replace')
        match = re.search(r'Ran (\d+) tests?', output)
        count = match.group(1) if match else '?'
        if result.returncode == 0:
            r.ok(f"{rel}: {count} tests passed")
        else:
            r.fail(f"{rel} failed:\n{output.strip()[-1500:]}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Validate the code-review skill')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='only print failures and the summary')
    args = parser.parse_args(argv)

    print(f"Validating code-review skill at {ROOT}")
    r = Report(quiet=args.quiet)

    check_structure(r)
    check_frontmatter(r)
    check_links(r)
    check_skill_index(r)
    check_agent_entry_points(r)
    check_adapter_limits(r)
    check_adapter_rules(r)
    check_doc_drift(r)
    check_script_tests(r)

    print('\n' + '=' * 60)
    print(f"Passed: {r.passes}   Warnings: {len(r.warnings)}   Failures: {len(r.failures)}")
    if r.failures:
        print('\nFailures:')
        for f in r.failures:
            print(f"  - {f}")
        print('=' * 60)
        return 1
    print('All checks passed.')
    print('=' * 60)
    return 0


if __name__ == '__main__':
    sys.exit(main())
