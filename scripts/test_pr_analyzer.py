#!/usr/bin/env python3
"""Tests for pr-analyzer.py (stdlib unittest, no extra deps)."""

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import unittest

# The script has a hyphen in its name, so load it by path.
_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    'pr_analyzer', os.path.join(_HERE, 'pr-analyzer.py')
)
pr_analyzer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr_analyzer)

# Convenient aliases
FileStats = pr_analyzer.FileStats


# ═══════════════════════════════════════════════════════════════
# parse_diff — filename extraction (existing tests)
# ═══════════════════════════════════════════════════════════════

class ParseDiffFilenameTest(unittest.TestCase):
    def test_lib_prefixed_path(self):
        # "lib/" embeds a literal "b/" that the old regex swallowed.
        diff = (
            "diff --git a/lib/foo.py b/lib/foo.py\n"
            "index 1234567..89abcde 100644\n"
            "--- a/lib/foo.py\n"
            "+++ b/lib/foo.py\n"
            "@@ -1,2 +1,3 @@\n"
            " unchanged\n"
            "+added line\n"
            "-removed line\n"
        )
        files = pr_analyzer.parse_diff(diff)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].filename, 'lib/foo.py')
        self.assertEqual(files[0].additions, 1)
        self.assertEqual(files[0].deletions, 1)

    def test_normal_path(self):
        diff = (
            "diff --git a/src/main.py b/src/main.py\n"
            "index 1111111..2222222 100644\n"
            "--- a/src/main.py\n"
            "+++ b/src/main.py\n"
            "@@ -0,0 +1 @@\n"
            "+print('hi')\n"
        )
        files = pr_analyzer.parse_diff(diff)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].filename, 'src/main.py')

    def test_other_embedded_b_slash_prefixes(self):
        # web/ and db/ also contain a literal "b/".
        diff = (
            "diff --git a/web/x.js b/web/x.js\n"
            "+++ b/web/x.js\n"
            "+console.log(1)\n"
            "diff --git a/db/y.sql b/db/y.sql\n"
            "+++ b/db/y.sql\n"
            "+SELECT 1;\n"
        )
        files = pr_analyzer.parse_diff(diff)
        self.assertEqual([f.filename for f in files], ['web/x.js', 'db/y.sql'])

    def test_rename_falls_back_to_b_side(self):
        diff = (
            "diff --git a/old/name.py b/new/name.py\n"
            "similarity index 100%\n"
            "rename from old/name.py\n"
            "rename to new/name.py\n"
        )
        files = pr_analyzer.parse_diff(diff)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].filename, 'new/name.py')


# ═══════════════════════════════════════════════════════════════
# detect_language
# ═══════════════════════════════════════════════════════════════

class DetectLanguageTest(unittest.TestCase):
    def test_common_extensions(self):
        cases = {
            'app.py': 'Python',
            'index.ts': 'TypeScript',
            'main.rs': 'Rust',
            'handler.go': 'Go',
            'App.java': 'Java',
            'Activity.kt': 'Kotlin',
            'ViewController.swift': 'Swift',
            'app.tsx': 'TypeScript/React',
            'style.css': 'CSS',
            'query.sql': 'SQL',
        }
        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                self.assertEqual(pr_analyzer.detect_language(filename), expected)

    def test_unknown_extension(self):
        self.assertEqual(pr_analyzer.detect_language('data.xyz'), 'unknown')
        self.assertEqual(pr_analyzer.detect_language('Makefile'), 'unknown')

    def test_cpp_variants(self):
        for ext in ('.cpp', '.hpp', '.cc', '.cxx', '.hh', '.hxx'):
            with self.subTest(ext=ext):
                self.assertEqual(pr_analyzer.detect_language(f'file{ext}'), 'C++')

    def test_asset_extensions_named_not_unknown(self):
        self.assertEqual(pr_analyzer.detect_language('logo.png'), 'Image')
        self.assertEqual(pr_analyzer.detect_language('icon.svg'), 'SVG')
        self.assertEqual(pr_analyzer.detect_language('body.woff2'), 'Font')

    def test_extra_source_extensions(self):
        self.assertEqual(pr_analyzer.detect_language('mod.mjs'), 'JavaScript')
        self.assertEqual(pr_analyzer.detect_language('build.gradle.kts'), 'Kotlin')
        self.assertEqual(pr_analyzer.detect_language('deploy.sh'), 'Shell')
        self.assertEqual(pr_analyzer.detect_language('main.tf'), 'Terraform')

    def test_jvm_dotnet_test_names(self):
        self.assertTrue(pr_analyzer.is_test_file('src/FooTest.java'))
        self.assertTrue(pr_analyzer.is_test_file('src/BarTests.cs'))
        self.assertFalse(pr_analyzer.is_test_file('src/Foo.java'))


# ═══════════════════════════════════════════════════════════════
# is_test_file
# ═══════════════════════════════════════════════════════════════

class IsTestFileTest(unittest.TestCase):
    def test_python_test_prefix(self):
        self.assertTrue(pr_analyzer.is_test_file('tests/test_handler.py'))
        self.assertTrue(pr_analyzer.is_test_file('test_utils.py'))

    def test_python_test_suffix(self):
        self.assertTrue(pr_analyzer.is_test_file('handler_test.py'))

    def test_rust_test_suffix(self):
        self.assertTrue(pr_analyzer.is_test_file('src/my_module_test.rs'))
        self.assertTrue(pr_analyzer.is_test_file('parser_test.rs'))

    def test_go_test_suffix(self):
        self.assertTrue(pr_analyzer.is_test_file('handler_test.go'))
        self.assertTrue(pr_analyzer.is_test_file('pkg/auth_test.go'))

    def test_js_ts_test_and_spec(self):
        self.assertTrue(pr_analyzer.is_test_file('handler.test.ts'))
        self.assertTrue(pr_analyzer.is_test_file('utils.spec.js'))
        self.assertTrue(pr_analyzer.is_test_file('App.test.tsx'))

    def test_tests_directory(self):
        self.assertTrue(pr_analyzer.is_test_file('tests/conftest.py'))
        self.assertTrue(pr_analyzer.is_test_file('test/helpers.js'))

    def test_dunder_tests_directory(self):
        self.assertTrue(pr_analyzer.is_test_file('__tests__/Button.test.tsx'))

    def test_non_test_files_rejected(self):
        self.assertFalse(pr_analyzer.is_test_file('handler.go'))
        self.assertFalse(pr_analyzer.is_test_file('module.rs'))
        self.assertFalse(pr_analyzer.is_test_file('src/utils.py'))
        self.assertFalse(pr_analyzer.is_test_file('lib/parser.js'))
        self.assertFalse(pr_analyzer.is_test_file('contest.py'))

    def test_test_substring_not_matched(self):
        """Files containing 'test_' as substring must NOT be flagged."""
        self.assertFalse(pr_analyzer.is_test_file('latest_report.py'))
        self.assertFalse(pr_analyzer.is_test_file('contest_utils.py'))
        self.assertFalse(pr_analyzer.is_test_file('src/latest_handler.py'))


# ═══════════════════════════════════════════════════════════════
# is_config_file
# ═══════════════════════════════════════════════════════════════

class IsConfigFileTest(unittest.TestCase):
    def test_known_json_configs(self):
        self.assertTrue(pr_analyzer.is_config_file('package.json'))
        self.assertTrue(pr_analyzer.is_config_file('tsconfig.json'))
        self.assertTrue(pr_analyzer.is_config_file('.eslintrc.json'))

    def test_known_yaml_configs(self):
        self.assertTrue(pr_analyzer.is_config_file('docker-compose.yml'))
        self.assertTrue(pr_analyzer.is_config_file('.github/workflows/ci.yml'))
        self.assertTrue(pr_analyzer.is_config_file('.prettierrc.yml'))

    def test_known_toml_configs(self):
        self.assertTrue(pr_analyzer.is_config_file('Cargo.toml'))
        self.assertTrue(pr_analyzer.is_config_file('pyproject.toml'))

    def test_env_files(self):
        self.assertTrue(pr_analyzer.is_config_file('.env'))
        self.assertTrue(pr_analyzer.is_config_file('.env.local'))
        self.assertTrue(pr_analyzer.is_config_file('.env.production'))

    def test_config_in_filename(self):
        self.assertTrue(pr_analyzer.is_config_file('app.config.ts'))
        self.assertTrue(pr_analyzer.is_config_file('database_config.yml'))

    def test_data_files_rejected(self):
        """Data files must NOT be flagged as config."""
        self.assertFalse(pr_analyzer.is_config_file('data.json'))
        self.assertFalse(pr_analyzer.is_config_file('openapi.yaml'))
        self.assertFalse(pr_analyzer.is_config_file('swagger.json'))
        self.assertFalse(pr_analyzer.is_config_file('fixtures/sample.yml'))
        self.assertFalse(pr_analyzer.is_config_file('translations.json'))
        self.assertFalse(pr_analyzer.is_config_file('schema.toml'))

    def test_config_directory(self):
        self.assertTrue(pr_analyzer.is_config_file('config/settings.yaml'))
        self.assertTrue(pr_analyzer.is_config_file('config/database.yml'))
        self.assertTrue(pr_analyzer.is_config_file('src/config/settings.json'))

    def test_source_files_rejected(self):
        self.assertFalse(pr_analyzer.is_config_file('src/index.ts'))
        self.assertFalse(pr_analyzer.is_config_file('lib/utils.py'))


# ═══════════════════════════════════════════════════════════════
# calculate_complexity
# ═══════════════════════════════════════════════════════════════

class CalculateComplexityTest(unittest.TestCase):
    def test_empty_files(self):
        self.assertEqual(pr_analyzer.calculate_complexity([]), 0.0)

    def test_small_simple_change(self):
        files = [FileStats(filename='app.py', additions=5, deletions=2,
                           language='Python')]
        score = pr_analyzer.calculate_complexity(files)
        self.assertLess(score, 0.3)

    def test_large_multi_language_change(self):
        files = [
            FileStats(filename='app.py', additions=300, deletions=100, language='Python'),
            FileStats(filename='main.rs', additions=200, deletions=50, language='Rust'),
            FileStats(filename='index.ts', additions=150, deletions=80, language='TypeScript'),
            FileStats(filename='handler.go', additions=100, deletions=30, language='Go'),
            FileStats(filename='App.tsx', additions=50, deletions=20, language='TypeScript/React'),
        ]
        score = pr_analyzer.calculate_complexity(files)
        self.assertGreater(score, 0.5)

    def test_test_heavy_change_is_lower(self):
        """Changes with high test ratio should have lower complexity."""
        prod_files = [FileStats(filename='app.py', additions=100, deletions=50,
                                language='Python')]
        test_files = [
            FileStats(filename='app.py', additions=100, deletions=50,
                      language='Python'),
            FileStats(filename='tests/test_app.py', additions=100, deletions=0,
                      language='Python', is_test=True),
        ]
        score_prod = pr_analyzer.calculate_complexity(prod_files)
        score_test = pr_analyzer.calculate_complexity(test_files)
        self.assertLess(score_test, score_prod)


# ═══════════════════════════════════════════════════════════════
# identify_risk_factors
# ═══════════════════════════════════════════════════════════════

class IdentifyRiskFactorsTest(unittest.TestCase):
    def test_large_pr_flagged(self):
        files = [FileStats(filename='big.py', additions=300, deletions=200,
                           language='Python')]
        risks = pr_analyzer.identify_risk_factors(files)
        self.assertTrue(any('Large PR' in r for r in risks))

    def test_no_tests_flagged(self):
        files = [FileStats(filename='app.py', additions=40, deletions=20,
                           language='Python')]
        risks = pr_analyzer.identify_risk_factors(files)
        self.assertTrue(any(pr_analyzer.RISK_NO_TESTS in r for r in risks))

    def test_with_tests_not_flagged(self):
        files = [
            FileStats(filename='app.py', additions=40, deletions=20,
                      language='Python'),
            FileStats(filename='tests/test_app.py', additions=30, deletions=0,
                      language='Python', is_test=True),
        ]
        risks = pr_analyzer.identify_risk_factors(files)
        self.assertFalse(any(pr_analyzer.RISK_NO_TESTS in r for r in risks))

    def test_security_sensitive_file(self):
        files = [FileStats(filename='src/auth/login.py', additions=10, deletions=5,
                           language='Python')]
        risks = pr_analyzer.identify_risk_factors(files)
        self.assertTrue(any('Security-sensitive' in r for r in risks))

    def test_database_migration(self):
        files = [FileStats(filename='migrations/001_init.sql', additions=20, deletions=0,
                           language='SQL')]
        risks = pr_analyzer.identify_risk_factors(files)
        self.assertTrue(any('Database' in r for r in risks))

    def test_test_substring_files_still_flag_no_tests(self):
        """Files like latest_report.py must not suppress NO_TEST_CHANGES."""
        files = [
            FileStats(filename='latest_report.py', additions=40, deletions=20,
                      language='Python'),
            FileStats(filename='contest_utils.py', additions=30, deletions=10,
                      language='Python'),
        ]
        risks = pr_analyzer.identify_risk_factors(files)
        self.assertTrue(any(pr_analyzer.RISK_NO_TESTS in r for r in risks))


# ═══════════════════════════════════════════════════════════════
# generate_suggestions
# ═══════════════════════════════════════════════════════════════

class GenerateSuggestionsTest(unittest.TestCase):
    def test_returns_list(self):
        files = [FileStats(filename='app.py', additions=10, deletions=5,
                           language='Python')]
        result = pr_analyzer.generate_suggestions(files, 0.1, [])
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_large_pr_split_suggestion(self):
        files = [FileStats(filename='big.py', additions=600, deletions=300,
                           language='Python')]
        result = pr_analyzer.generate_suggestions(files, 0.3, [])
        self.assertTrue(any('splitting' in s.lower() for s in result))

    def test_no_tests_suggestion(self):
        files = [FileStats(filename='app.py', additions=40, deletions=20,
                           language='Python')]
        risks = [f"{pr_analyzer.RISK_NO_TESTS}: no tests"]
        result = pr_analyzer.generate_suggestions(files, 0.2, risks)
        self.assertTrue(any('test' in s.lower() for s in result))

    def test_rust_suggestion(self):
        files = [FileStats(filename='lib.rs', additions=10, deletions=5,
                           language='Rust')]
        result = pr_analyzer.generate_suggestions(files, 0.1, [])
        self.assertTrue(any('unwrap' in s.lower() for s in result))


# ═══════════════════════════════════════════════════════════════
# analyze_pr — end-to-end integration
# ═══════════════════════════════════════════════════════════════

class AnalyzePRTest(unittest.TestCase):
    def test_end_to_end(self):
        diff = (
            "diff --git a/src/app.py b/src/app.py\n"
            "index 1111111..2222222 100644\n"
            "--- a/src/app.py\n"
            "+++ b/src/app.py\n"
            "@@ -1,3 +1,5 @@\n"
            " import os\n"
            "+import sys\n"
            "+import json\n"
            " def main():\n"
            "+    print('hello')\n"
            "+    return 0\n"
            "diff --git a/tests/test_app.py b/tests/test_app.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/tests/test_app.py\n"
            "@@ -0,0 +1,3 @@\n"
            "+from app import main\n"
            "+def test_main():\n"
            "+    assert main() == 0\n"
        )
        analysis = pr_analyzer.analyze_pr(diff)

        self.assertEqual(analysis.total_files, 2)
        self.assertEqual(analysis.total_additions, 7)  # 4 + 3
        self.assertEqual(analysis.total_deletions, 0)
        self.assertGreater(len(analysis.suggestions), 0)
        self.assertIn('XS (Extra Small)', analysis.size_category)

        # Verify test file was detected
        test_file = [f for f in analysis.files if 'test' in f.filename][0]
        self.assertTrue(test_file.is_test)

        # Verify no "NO_TEST_CHANGES" risk since tests are present
        self.assertFalse(
            any(pr_analyzer.RISK_NO_TESTS in r for r in analysis.risk_factors)
        )

    def test_empty_diff(self):
        analysis = pr_analyzer.analyze_pr("")
        self.assertEqual(analysis.total_files, 0)
        self.assertEqual(analysis.complexity_score, 0.0)


class ParseDiffHunkTrackingTest(unittest.TestCase):
    """Counting must happen only inside hunks, so headers and content that
    starts with ---/+++ are both handled correctly."""

    def test_markdown_horizontal_rules_are_counted(self):
        # "---" and "+++" as *content* were previously dropped as headers.
        diff = (
            "diff --git a/doc.md b/doc.md\n"
            "--- a/doc.md\n"
            "+++ b/doc.md\n"
            "@@ -1,2 +1,2 @@\n"
            "---\n"
            "+++\n"
        )
        files = pr_analyzer.parse_diff(diff)
        self.assertEqual((files[0].additions, files[0].deletions), (1, 1))

    def test_file_headers_are_not_counted(self):
        diff = (
            "diff --git a/a.py b/a.py\n"
            "index 1111111..2222222 100644\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1,2 +1,2 @@\n"
            " context\n"
            "-old\n"
            "+new\n"
        )
        files = pr_analyzer.parse_diff(diff)
        self.assertEqual((files[0].additions, files[0].deletions), (1, 1))

    def test_cpp_decrement_content_counted(self):
        diff = (
            "diff --git a/m.cpp b/m.cpp\n"
            "--- a/m.cpp\n"
            "+++ b/m.cpp\n"
            "@@ -1,1 +1,1 @@\n"
            "---x;\n"
            "+++y;\n"
        )
        files = pr_analyzer.parse_diff(diff)
        self.assertEqual((files[0].additions, files[0].deletions), (1, 1))

    def test_no_newline_marker_not_counted(self):
        diff = (
            "diff --git a/a.txt b/a.txt\n"
            "--- a/a.txt\n"
            "+++ b/a.txt\n"
            "@@ -1 +1 @@\n"
            "-a\n"
            "\\ No newline at end of file\n"
            "+b\n"
        )
        files = pr_analyzer.parse_diff(diff)
        self.assertEqual((files[0].additions, files[0].deletions), (1, 1))

    def test_multiple_hunks_in_one_file(self):
        diff = (
            "diff --git a/a.py b/a.py\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1,2 +1,3 @@\n"
            "+one\n"
            "@@ -10,2 +11,3 @@\n"
            "+two\n"
            "-three\n"
        )
        files = pr_analyzer.parse_diff(diff)
        self.assertEqual((files[0].additions, files[0].deletions), (2, 1))

    def test_path_with_spaces(self):
        diff = (
            "diff --git a/my dir/a.py b/my dir/a.py\n"
            "--- a/my dir/a.py\n"
            "+++ b/my dir/a.py\n"
            "@@ -1 +1 @@\n"
            "+x\n"
        )
        files = pr_analyzer.parse_diff(diff)
        self.assertEqual(files[0].filename, 'my dir/a.py')


class BinaryFileTest(unittest.TestCase):
    def test_binary_file_detected(self):
        diff = (
            "diff --git a/logo.png b/logo.png\n"
            "index 1111111..2222222 100644\n"
            "Binary files a/logo.png and b/logo.png differ\n"
        )
        files = pr_analyzer.parse_diff(diff)
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].is_binary)
        self.assertEqual((files[0].additions, files[0].deletions), (0, 0))

    def test_git_binary_patch_detected(self):
        diff = (
            "diff --git a/blob.bin b/blob.bin\n"
            "GIT binary patch\n"
            "literal 8\n"
        )
        files = pr_analyzer.parse_diff(diff)
        self.assertTrue(files[0].is_binary)

    def test_binary_change_is_a_risk(self):
        files = [FileStats(filename='logo.png', is_binary=True)]
        risks = pr_analyzer.identify_risk_factors(files)
        self.assertTrue(any('Binary' in r for r in risks))


class SecuritySensitiveTest(unittest.TestCase):
    def test_security_paths_matched(self):
        for path in (
            'src/auth/login.py',
            'app/security/filter.java',
            'lib/session_store.rb',
            'internal/jwt.go',
            'config/secrets.yml',
            '.env.production',
            'api/permissions.ts',
        ):
            with self.subTest(path=path):
                self.assertTrue(pr_analyzer.is_security_sensitive(path))

    def test_substring_false_positives_rejected(self):
        """Whole-token matching: these must NOT be flagged."""
        for path in (
            'author.py',          # contains "auth"
            'authorship/list.py',
            'tokenizer.py',       # contains "token"
            'src/tokenize.rs',
            'passwordless_demo/readme.md',
            'securely_named_nothing.txt',
        ):
            with self.subTest(path=path):
                self.assertFalse(pr_analyzer.is_security_sensitive(path))

    def test_all_sensitive_files_reported(self):
        """The old code reported only the first match."""
        files = [
            FileStats(filename='auth/a.py', additions=5),
            FileStats(filename='secrets/b.py', additions=5),
        ]
        risks = pr_analyzer.identify_risk_factors(files)
        sec = [r for r in risks if r.startswith('Security-sensitive')]
        self.assertEqual(len(sec), 1)
        self.assertIn('auth/a.py', sec[0])
        self.assertIn('secrets/b.py', sec[0])

    def test_many_sensitive_files_are_capped(self):
        files = [FileStats(filename=f'auth/f{i}.py', additions=1) for i in range(6)]
        risks = pr_analyzer.identify_risk_factors(files)
        sec = next(r for r in risks if r.startswith('Security-sensitive'))
        self.assertIn('+3 more', sec)

    def test_security_suggestion_added(self):
        files = [FileStats(filename='auth/login.py', additions=5)]
        risks = pr_analyzer.identify_risk_factors(files)
        suggestions = pr_analyzer.generate_suggestions(files, 0.1, risks)
        self.assertTrue(any('security-review-guide' in s for s in suggestions))


class OutputPortabilityTest(unittest.TestCase):
    """The report must render in any agent environment: terminals, piped
    stdout on Windows, and notebook/sandbox streams."""

    def _analysis(self):
        return pr_analyzer.analyze_pr(
            "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a\n+b\n"
        )

    def test_ascii_fallback_has_no_emoji(self):
        buf = io.StringIO()
        pr_analyzer.print_analysis(self._analysis(), stream=buf, emoji=False)
        text = buf.getvalue()
        self.assertIn('[SUMMARY]', text)
        self.assertTrue(text.isascii(), 'ASCII mode must emit only ASCII')

    def test_emoji_mode_renders(self):
        buf = io.StringIO()
        pr_analyzer.print_analysis(self._analysis(), stream=buf, emoji=True)
        self.assertIn('📊', buf.getvalue())

    def test_supports_emoji_detection(self):
        self.assertFalse(pr_analyzer.supports_emoji(_FakeStream('ascii')))
        self.assertFalse(pr_analyzer.supports_emoji(_FakeStream('cp1252')))
        self.assertTrue(pr_analyzer.supports_emoji(_FakeStream('utf-8')))
        # A stream with no declared encoding (notebook shim) is assumed UTF-8.
        self.assertTrue(pr_analyzer.supports_emoji(_FakeStream(None)))

    def test_report_survives_stream_without_reconfigure(self):
        """ChatGPT Code Interpreter / Jupyter stdout has no reconfigure()."""
        script = (
            'import sys, io, importlib.util\n'
            'class Out(io.TextIOBase):\n'
            '    encoding = None\n'
            '    def write(self, s):\n'
            '        sys.__stdout__.buffer.write(s.encode("utf-8"))\n'
            '        return len(s)\n'
            '    def isatty(self):\n'
            '        return False\n'
            'spec = importlib.util.spec_from_file_location("pa", %r)\n'
            'm = importlib.util.module_from_spec(spec)\n'
            'spec.loader.exec_module(m)\n'
            'sys.stdout = Out()\n'
            'rc = m.main(["-f", %r])\n'
            'sys.stdout = sys.__stdout__\n'
            'print("RC", rc)\n'
        ) % (os.path.join(_HERE, 'pr-analyzer.py'), os.path.join(_HERE, '..', 'README.md'))
        result = subprocess.run([sys.executable, '-c', script],
                                capture_output=True)
        self.assertEqual(result.returncode, 0,
                         result.stderr.decode(errors='replace'))

    def test_json_output_is_machine_readable(self):
        result = subprocess.run(
            [sys.executable, os.path.join(_HERE, 'pr-analyzer.py'), '--json'],
            input=b"diff --git a/a.py b/a.py\n@@ -1 +1 @@\n+x\n",
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0,
                         result.stderr.decode(errors='replace'))
        payload = json.loads(result.stdout.decode('utf-8'))
        self.assertEqual(payload['total_files'], 1)
        self.assertEqual(payload['total_additions'], 1)
        self.assertIn('risk_factors', payload)

    def test_no_emoji_flag_under_ascii_stdout(self):
        result = subprocess.run(
            [sys.executable, os.path.join(_HERE, 'pr-analyzer.py'), '--no-emoji', '-s'],
            input=b"diff --git a/a.py b/a.py\n@@ -1 +1 @@\n+x\n",
            capture_output=True,
            env={**os.environ, 'PYTHONIOENCODING': 'ascii'},
        )
        self.assertEqual(result.returncode, 0,
                         result.stderr.decode(errors='replace'))
        self.assertIn(b'[SUMMARY]', result.stdout)

    def test_main_returns_exit_code_for_empty_diff(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = pr_analyzer.main(['-f', os.devnull])
        self.assertEqual(rc, 1)


class _FakeStream:
    """Minimal stream stand-in for encoding detection tests."""

    def __init__(self, encoding):
        self.encoding = encoding


class CliOutputEncodingTest(unittest.TestCase):
    def test_report_prints_when_stdout_is_not_utf8(self):
        # Piped stdout on Windows is cp1252; the emoji report used to crash there.
        result = subprocess.run(
            [sys.executable, os.path.join(_HERE, 'pr-analyzer.py')],
            input=b"diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n",
            capture_output=True,
            env={**os.environ, 'PYTHONIOENCODING': 'ascii'},
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        self.assertIn('PR ANALYSIS REPORT', result.stdout.decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
