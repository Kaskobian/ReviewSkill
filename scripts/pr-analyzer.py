#!/usr/bin/env python3
"""
PR Analyzer - Analyze PR complexity and suggest review approach.

Usage:
    python pr-analyzer.py [--diff-file FILE] [--stats] [--json] [--no-emoji]

    Or pipe diff directly:
    git diff main...HEAD | python pr-analyzer.py

Portability: standard library only, Python 3.8+. Runs unchanged in a terminal,
a notebook kernel (ChatGPT Code Interpreter), or an agent sandbox.
"""

import json
import os
import sys
import re
import argparse
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, TextIO

RISK_NO_TESTS = "NO_TEST_CHANGES"

# Path tokens that mark a file as security-sensitive. Matched as whole tokens
# (path split on non-alphanumerics) so "author.py" is not read as "auth" and
# "tokenizer.py" is not read as "token".
SECURITY_TOKENS = frozenset({
    'auth', 'authn', 'authz', 'authentication', 'authorization',
    'security', 'secure', 'crypto', 'cryptography',
    'password', 'passwords', 'passwd',
    'token', 'tokens', 'jwt', 'oauth', 'oidc', 'saml',
    'secret', 'secrets', 'credential', 'credentials', 'keystore',
    'session', 'sessions', 'cookie', 'cookies',
    'login', 'logout', 'signin', 'signup',
    'permission', 'permissions', 'acl', 'rbac',
})

# Emoji label → ASCII fallback, for streams that cannot encode emoji.
_LABELS = {
    'summary': ('📊', '[SUMMARY]'),
    'size': ('📏', '[SIZE]'),
    'risk': ('⚠️ ', '[RISK]'),
    'suggest': ('💡', '[SUGGESTIONS]'),
    'files': ('📁', '[FILES]'),
    'test': ('🧪', '[test]'),
    'config': ('⚙️', '[conf]'),
    'binary': ('📦', '[bin] '),
    'source': ('📄', '[src] '),
}


@dataclass
class FileStats:
    """Statistics for a single file."""
    filename: str
    additions: int = 0
    deletions: int = 0
    is_test: bool = False
    is_config: bool = False
    is_binary: bool = False
    language: str = "unknown"


@dataclass
class PRAnalysis:
    """Complete PR analysis results."""
    total_files: int
    total_additions: int
    total_deletions: int
    files: List[FileStats]
    complexity_score: float
    size_category: str
    estimated_review_time: int
    risk_factors: List[str]
    suggestions: List[str]


def detect_language(filename: str) -> str:
    """Detect programming language from filename."""
    _, ext = os.path.splitext(filename)
    extensions = {
        '.py': 'Python',
        '.js': 'JavaScript',
        '.mjs': 'JavaScript',
        '.cjs': 'JavaScript',
        '.ts': 'TypeScript',
        '.tsx': 'TypeScript/React',
        '.jsx': 'JavaScript/React',
        '.rs': 'Rust',
        '.go': 'Go',
        '.c': 'C',
        '.h': 'C/C++',
        '.cpp': 'C++',
        '.hpp': 'C++',
        '.cc': 'C++',
        '.cxx': 'C++',
        '.hh': 'C++',
        '.hxx': 'C++',
        '.java': 'Java',
        '.kt': 'Kotlin',
        '.kts': 'Kotlin',
        '.swift': 'Swift',
        '.rb': 'Ruby',
        '.php': 'PHP',
        '.cs': 'C#',
        '.vue': 'Vue',
        '.svelte': 'Svelte',
        '.sql': 'SQL',
        '.md': 'Markdown',
        '.json': 'JSON',
        '.yaml': 'YAML',
        '.yml': 'YAML',
        '.toml': 'TOML',
        '.css': 'CSS',
        '.scss': 'SCSS',
        '.sass': 'Sass',
        '.dart': 'Dart',
        '.less': 'Less',
        '.html': 'HTML',
        '.zig': 'Zig',
        '.ex': 'Elixir',
        '.exs': 'Elixir',
        '.erl': 'Erlang',
        '.scala': 'Scala',
        '.lua': 'Lua',
        '.sh': 'Shell',
        '.bash': 'Shell',
        '.tf': 'Terraform',
        '.proto': 'Protobuf',
        # Common binary/asset types, so the report does not call them "unknown".
        '.png': 'Image',
        '.jpg': 'Image',
        '.jpeg': 'Image',
        '.gif': 'Image',
        '.webp': 'Image',
        '.ico': 'Image',
        '.svg': 'SVG',
        '.pdf': 'Binary',
        '.zip': 'Binary',
        '.woff': 'Font',
        '.woff2': 'Font',
        '.ttf': 'Font',
    }
    return extensions.get(ext.lower(), 'unknown')


def is_test_file(filename: str) -> bool:
    """Check if file is a test file."""
    test_patterns = [
        r'(?:^|/)test_[^/]+\.py$',   # Python: test_handler.py (anchored to path segment)
        r'[^/]+_test\.',             # *_test.<ext> — Rust, Go, etc.
        r'[^/]+\.test\.(js|ts|tsx|jsx|mjs|cjs)$',  # JS/TS: handler.test.ts
        r'[^/]+\.spec\.(js|ts|tsx|jsx|mjs|cjs)$',  # JS/TS: handler.spec.ts
        r'(?:^|/)tests?/',           # tests/ or test/ directory
        r'(?:^|/)__tests__/',        # __tests__/ directory
        r'(?:^|/)spec/',             # spec/ directory (Ruby, etc.)
        r'Tests?\.(java|kt|cs)$',    # JVM/.NET: FooTest.java, BarTests.cs
    ]
    return any(re.search(p, filename) for p in test_patterns)


def is_config_file(filename: str) -> bool:
    """Check if file is a configuration file.

    Uses explicit known-name matching to avoid flagging data files
    like data.json, openapi.yaml, or swagger.json as config.
    """
    basename = os.path.basename(filename)

    # Env files (.env, .env.local, .env.production, …)
    if basename.startswith('.env'):
        return True

    # Known config filenames (exact match)
    known_config_names = {
        'package.json', 'package-lock.json',
        'tsconfig.json', 'jsconfig.json',
        'babel.config.json', 'babel.config.js',
        'webpack.config.js', 'webpack.config.ts',
        'rollup.config.js', 'vite.config.ts', 'vite.config.js',
        '.eslintrc.json', '.eslintrc.js', '.eslintrc.yml',
        '.prettierrc.json', '.prettierrc.yml', '.prettierrc.js',
        'jest.config.js', 'jest.config.ts',
        'vitest.config.ts', 'vitest.config.js',
        'tailwind.config.js', 'tailwind.config.ts',
        'postcss.config.js',
        'docker-compose.yml', 'docker-compose.yaml',
        'Dockerfile',
        'Makefile', 'CMakeLists.txt',
        'pyproject.toml', 'poetry.toml', 'Pipfile',
        'setup.cfg', 'setup.py', 'tox.ini',
        'Cargo.toml', 'Cargo.lock',
        'go.mod', 'go.sum',
        'Gemfile', 'Gemfile.lock',
        'composer.json', 'composer.lock',
        'Podfile', 'Package.swift',
        '.gitignore', '.gitattributes',
        'gradle.properties', 'build.gradle', 'build.gradle.kts',
        'settings.gradle', 'settings.gradle.kts',
    }
    if basename in known_config_names:
        return True

    # Known config path patterns
    config_path_patterns = [
        r'\.github/workflows/[^/]+\.ya?ml$',
        r'\.vscode/',
        r'\.idea/',
    ]
    if any(re.search(p, filename) for p in config_path_patterns):
        return True

    # Files with "config" in the name (e.g. app.config.ts, database_config.yml)
    if re.search(r'config\.', basename):
        return True

    # Files under a config/ directory
    if re.search(r'(?:^|/)config/', filename):
        return True

    return False


def path_tokens(filename: str) -> List[str]:
    """Split a path into lowercase alphanumeric tokens for whole-word matching."""
    return [t for t in re.split(r'[^0-9a-z]+', filename.lower()) if t]


def is_security_sensitive(filename: str) -> bool:
    """Whether a path looks security-sensitive, by whole-token match.

    'src/auth/login.py' matches; 'author.py' and 'tokenizer.py' do not.
    """
    if os.path.basename(filename).startswith('.env'):
        return True
    return bool(SECURITY_TOKENS.intersection(path_tokens(filename)))


def parse_diff(diff_content: str) -> List[FileStats]:
    """Parse git diff output and extract file statistics.

    Added/removed lines are counted only inside a hunk (after an ``@@`` header),
    so the ``---``/``+++`` file headers are never miscounted and content lines
    that legitimately start with ``---``/``+++`` (Markdown rules, C++ decrements)
    are not silently dropped.
    """
    files: List[FileStats] = []
    current_file: Optional[FileStats] = None
    in_hunk = False

    for line in diff_content.split('\n'):
        # New file header
        if line.startswith('diff --git'):
            if current_file:
                files.append(current_file)
            in_hunk = False
            # "diff --git a/<path> b/<path>" — match the b/ side via a
            # backreference so a literal "b/" inside paths like lib/, web/ or
            # db/ can't be mistaken for the prefix. Renames have differing
            # paths, so fall back to the b/ side after the separating space.
            match = re.match(r'diff --git a/(.+?) b/\1$', line)
            if not match:
                match = re.search(r' b/(.+)$', line)
            if match:
                filename = match.group(1)
                current_file = FileStats(
                    filename=filename,
                    language=detect_language(filename),
                    is_test=is_test_file(filename),
                    is_config=is_config_file(filename),
                )
            else:
                current_file = None
            continue

        if current_file is None:
            continue

        if line.startswith('@@'):
            in_hunk = True
            continue

        # Binary payloads carry no countable line changes.
        if line.startswith('Binary files ') or line.startswith('GIT binary patch'):
            current_file.is_binary = True
            in_hunk = False
            continue

        if not in_hunk:
            continue

        if line.startswith('+'):
            current_file.additions += 1
        elif line.startswith('-'):
            current_file.deletions += 1
        # ' context', '\\ No newline at end of file' and blank lines: ignored.

    if current_file:
        files.append(current_file)

    return files


def calculate_complexity(files: List[FileStats]) -> float:
    """Calculate complexity score (0-1 scale)."""
    if not files:
        return 0.0

    total_changes = sum(f.additions + f.deletions for f in files)

    # Base complexity from size
    size_factor = min(total_changes / 1000, 1.0)

    # Factor for number of files
    file_factor = min(len(files) / 20, 1.0)

    # Factor for non-test code ratio
    test_lines = sum(f.additions + f.deletions for f in files if f.is_test)
    non_test_ratio = 1 - (test_lines / max(total_changes, 1))

    # Factor for language diversity (binary assets are not a reviewed language)
    languages = set(f.language for f in files
                    if f.language != 'unknown' and not f.is_binary)
    lang_factor = min(len(languages) / 5, 1.0)

    complexity = (
        size_factor * 0.4 +
        file_factor * 0.2 +
        non_test_ratio * 0.2 +
        lang_factor * 0.2
    )

    return round(complexity, 2)


def categorize_size(total_changes: int) -> str:
    """Categorize PR size."""
    if total_changes < 50:
        return "XS (Extra Small)"
    elif total_changes < 200:
        return "S (Small)"
    elif total_changes < 400:
        return "M (Medium)"
    elif total_changes < 800:
        return "L (Large)"
    else:
        return "XL (Extra Large) - Consider splitting"


def estimate_review_time(files: List[FileStats], complexity: float) -> int:
    """Estimate review time in minutes."""
    total_changes = sum(f.additions + f.deletions for f in files)

    # Base time: ~1 minute per 20 lines
    base_time = total_changes / 20

    # Adjust for complexity
    adjusted_time = base_time * (1 + complexity)

    # Minimum 5 minutes, maximum 120 minutes
    return max(5, min(120, int(adjusted_time)))


def identify_risk_factors(files: List[FileStats]) -> List[str]:
    """Identify potential risk factors in the PR."""
    risks = []

    total_changes = sum(f.additions + f.deletions for f in files)
    test_changes = sum(f.additions + f.deletions for f in files if f.is_test)

    if total_changes > 400:
        risks.append("Large PR (>400 lines) - harder to review thoroughly")

    if test_changes == 0 and total_changes > 50:
        risks.append(f"{RISK_NO_TESTS}: No test changes - verify test coverage")

    if total_changes > 100 and test_changes / max(total_changes, 1) < 0.2:
        risks.append("Low test ratio (<20%) - consider adding more tests")

    # Security-sensitive files: report every match, not just the first.
    sensitive = [f.filename for f in files if is_security_sensitive(f.filename)]
    if sensitive:
        shown = ', '.join(sensitive[:3])
        if len(sensitive) > 3:
            shown += f" (+{len(sensitive) - 3} more)"
        risks.append(f"Security-sensitive file(s): {shown}")

    # Database changes
    for f in files:
        if 'migration' in f.filename.lower() or f.language == 'SQL':
            risks.append("Database changes detected - review carefully")
            break

    # Config changes
    config_files = [f for f in files if f.is_config]
    if config_files:
        risks.append(f"Configuration changes in {len(config_files)} file(s)")

    # Binary blobs cannot be reviewed as text
    binary_files = [f for f in files if f.is_binary]
    if binary_files:
        risks.append(
            f"Binary file(s) changed: {len(binary_files)} - not reviewable as a "
            "diff; verify provenance and necessity"
        )

    return risks


def generate_suggestions(files: List[FileStats], complexity: float, risks: List[str]) -> List[str]:
    """Generate review suggestions."""
    suggestions = []

    total_changes = sum(f.additions + f.deletions for f in files)

    if total_changes > 800:
        suggestions.append("Consider splitting this PR into smaller, focused changes")

    if complexity > 0.7:
        suggestions.append("High complexity - allocate extra review time")
        suggestions.append("Consider pair reviewing for critical sections")

    if any(RISK_NO_TESTS in r for r in risks):
        suggestions.append("Request test additions before approval")

    if any(r.startswith('Security-sensitive') for r in risks):
        suggestions.append("Load reference/security-review-guide.md for this review")

    # Language-specific suggestions
    languages = set(f.language for f in files)
    if 'TypeScript' in languages or 'TypeScript/React' in languages:
        suggestions.append("Check for proper type usage (avoid 'any')")
    if 'Rust' in languages:
        suggestions.append("Check for unwrap() usage and error handling")
    if 'C' in languages or 'C++' in languages or 'C/C++' in languages:
        suggestions.append("Check for memory safety, bounds checks, and UB risks")
    if 'SQL' in languages:
        suggestions.append("Review for SQL injection and query performance")

    if not suggestions:
        suggestions.append("Standard review process should suffice")

    return suggestions


def analyze_pr(diff_content: str) -> PRAnalysis:
    """Perform complete PR analysis."""
    files = parse_diff(diff_content)

    total_additions = sum(f.additions for f in files)
    total_deletions = sum(f.deletions for f in files)
    total_changes = total_additions + total_deletions

    complexity = calculate_complexity(files)
    risks = identify_risk_factors(files)
    suggestions = generate_suggestions(files, complexity, risks)

    return PRAnalysis(
        total_files=len(files),
        total_additions=total_additions,
        total_deletions=total_deletions,
        files=files,
        complexity_score=complexity,
        size_category=categorize_size(total_changes),
        estimated_review_time=estimate_review_time(files, complexity),
        risk_factors=risks,
        suggestions=suggestions,
    )


def supports_emoji(stream: TextIO) -> bool:
    """Whether the stream's encoding can represent the report's emoji."""
    encoding = getattr(stream, 'encoding', None)
    if not encoding:
        # Notebook/agent streams often expose no encoding but accept UTF-8.
        return True
    try:
        '📊⚠️🧪'.encode(encoding)
    except (UnicodeEncodeError, LookupError, TypeError):
        return False
    return True


def _label(key: str, emoji: bool) -> str:
    return _LABELS[key][0] if emoji else _LABELS[key][1]


def print_analysis(
    analysis: PRAnalysis,
    show_files: bool = False,
    stream: Optional[TextIO] = None,
    emoji: Optional[bool] = None,
) -> None:
    """Print analysis results.

    ``emoji=None`` auto-detects from the stream encoding and falls back to
    ASCII labels, so the report never crashes on a non-UTF-8 console.
    """
    out = stream if stream is not None else sys.stdout
    if emoji is None:
        emoji = supports_emoji(out)
    bullet = '•' if emoji else '-'

    def w(text: str = '') -> None:
        print(text, file=out)

    w("\n" + "=" * 60)
    w("PR ANALYSIS REPORT")
    w("=" * 60)

    w(f"\n{_label('summary', emoji)} SUMMARY")
    w(f"   Files changed: {analysis.total_files}")
    w(f"   Additions: +{analysis.total_additions}")
    w(f"   Deletions: -{analysis.total_deletions}")
    w(f"   Total changes: {analysis.total_additions + analysis.total_deletions}")

    w(f"\n{_label('size', emoji)} SIZE: {analysis.size_category}")
    w(f"   Complexity score: {analysis.complexity_score}/1.0")
    w(f"   Estimated review time: ~{analysis.estimated_review_time} minutes")

    if analysis.risk_factors:
        w(f"\n{_label('risk', emoji)} RISK FACTORS:")
        for risk in analysis.risk_factors:
            w(f"   {bullet} {risk}")

    w(f"\n{_label('suggest', emoji)} SUGGESTIONS:")
    for suggestion in analysis.suggestions:
        w(f"   {bullet} {suggestion}")

    if show_files:
        w(f"\n{_label('files', emoji)} FILES:")
        # Group by language
        by_lang: Dict[str, List[FileStats]] = defaultdict(list)
        for f in analysis.files:
            by_lang[f.language].append(f)

        for lang, lang_files in sorted(by_lang.items()):
            w(f"\n   [{lang}]")
            for f in lang_files:
                if f.is_binary:
                    prefix = _label('binary', emoji)
                elif f.is_test:
                    prefix = _label('test', emoji)
                elif f.is_config:
                    prefix = _label('config', emoji)
                else:
                    prefix = _label('source', emoji)
                w(f"   {prefix} {f.filename} (+{f.additions}/-{f.deletions})")

    w("\n" + "=" * 60)


def analysis_to_json(analysis: PRAnalysis) -> str:
    """Serialize the analysis so an agent can consume it without parsing text."""
    return json.dumps(asdict(analysis), indent=2, ensure_ascii=False)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Analyze PR complexity')
    parser.add_argument('--diff-file', '-f', help='Path to diff file')
    parser.add_argument('--stats', '-s', action='store_true', help='Show file details')
    parser.add_argument('--json', action='store_true',
                        help='Emit machine-readable JSON instead of the text report')
    parser.add_argument('--no-emoji', action='store_true',
                        help='Force ASCII labels (default: auto-detect from stdout)')
    args = parser.parse_args(argv)

    # The report uses emoji; a piped stdout on Windows defaults to cp1252.
    # Notebook and agent-sandbox streams may not implement reconfigure() at
    # all, so this is best-effort — print_analysis falls back to ASCII labels.
    reconfigure = getattr(sys.stdout, 'reconfigure', None)
    if callable(reconfigure):
        try:
            reconfigure(encoding='utf-8', errors='replace')
        except (ValueError, OSError, TypeError):
            pass

    # Read diff from file or stdin
    try:
        if args.diff_file:
            with open(args.diff_file, 'r', encoding='utf-8', errors='replace') as f:
                diff_content = f.read()
        elif not sys.stdin.isatty():
            buffer = getattr(sys.stdin, 'buffer', None)
            if buffer is not None:
                diff_content = buffer.read().decode('utf-8', errors='replace')
            else:
                # Notebook stdin shims expose no .buffer.
                diff_content = sys.stdin.read()
        else:
            print("Usage: git diff main...HEAD | python pr-analyzer.py")
            print("       python pr-analyzer.py -f diff.txt")
            return 1
    except OSError as e:
        print(f"Error reading diff input: {e}", file=sys.stderr)
        return 1

    if not diff_content.strip():
        print("No diff content provided")
        return 1

    analysis = analyze_pr(diff_content)

    if args.json:
        print(analysis_to_json(analysis))
        return 0

    print_analysis(analysis, show_files=args.stats,
                   emoji=False if args.no_emoji else None)
    return 0


if __name__ == '__main__':
    sys.exit(main())
