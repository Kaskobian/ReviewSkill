#!/usr/bin/env python3
"""Tests for security-scan.py (stdlib unittest, no extra deps).

Each rule gets a positive case (vulnerable line is flagged) and, where a
common false positive exists, a negative case (safe line is not flagged).
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, 'security-scan.py')
_spec = importlib.util.spec_from_file_location('security_scan', _SCRIPT)
scan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan)


def rules_hit(code: str, filename: str):
    """Rule IDs flagged when `code` is the content of `filename`."""
    lines = list(enumerate(code.splitlines(), start=1))
    hits = scan.scan_lines(filename, lines, scan.file_kind(filename), scan.RULES)
    return {h.rule for h in hits}


class RuleCase(unittest.TestCase):
    def assertFlags(self, rule, code, filename):
        self.assertIn(rule, rules_hit(code, filename), f'{rule} should flag: {code!r}')

    def assertClean(self, rule, code, filename):
        self.assertNotIn(rule, rules_hit(code, filename), f'{rule} must not flag: {code!r}')


class CatalogTest(unittest.TestCase):
    def test_rule_ids_unique(self):
        ids = [r.id for r in scan.RULES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_rule_maps_to_known_category_and_cwe(self):
        for r in scan.RULES:
            with self.subTest(rule=r.id):
                self.assertIn(r.owasp, scan.OWASP)
                self.assertRegex(r.cwe, r'^CWE-\d+$')
                self.assertIn(r.confidence, scan.CONFIDENCE_RANK)
                self.assertTrue(r.verify and r.fix)
                r.compiled()  # every pattern compiles

    def test_all_ten_owasp_categories_covered(self):
        covered = {r.owasp for r in scan.RULES}
        # A06 Insecure Design is logic-level and has no pattern rules by design;
        # the audit guide covers it manually.
        for cat in ('A01', 'A02', 'A03', 'A04', 'A05', 'A07', 'A08', 'A09', 'A10'):
            self.assertIn(cat, covered)

    def test_llm_categories_covered(self):
        covered = {r.owasp for r in scan.RULES}
        for cat in ('LLM01', 'LLM05', 'LLM06'):
            self.assertIn(cat, covered)


class InjectionTest(RuleCase):
    def test_sql_fstring(self):
        self.assertFlags('INJ-SQL-FSTRING', 'cur.execute(f"SELECT * FROM u WHERE id={uid}")', 'a.py')

    def test_sql_parameterized_clean(self):
        code = 'cur.execute("SELECT * FROM u WHERE id = %s", (uid,))'
        for rule in ('INJ-SQL-FSTRING', 'INJ-SQL-FORMAT', 'INJ-SQL-CONCAT'):
            self.assertClean(rule, code, 'a.py')

    def test_sql_percent_format(self):
        self.assertFlags('INJ-SQL-FORMAT', 'cur.execute("SELECT * FROM u WHERE n=\'%s\'" % n)', 'a.py')

    def test_sql_concat_java_mixed_quotes(self):
        code = 's.executeQuery("SELECT * FROM t WHERE a = \'" + a + "\'");'
        self.assertFlags('INJ-SQL-CONCAT', code, 'Main.java')

    def test_sql_template_literal(self):
        self.assertFlags('INJ-SQL-TEMPLATE', 'db.query(`SELECT * FROM u WHERE id = ${req.query.id}`)', 's.js')

    def test_sql_tagged_template_clean(self):
        self.assertClean('INJ-SQL-TEMPLATE', 'db.query(sql`SELECT * FROM u WHERE id = ${id}`)', 's.js')

    def test_sql_sprintf_go(self):
        self.assertFlags('INJ-SQL-SPRINTF', 'q := fmt.Sprintf("SELECT * FROM u WHERE id = %s", id)', 'm.go')

    def test_sql_ruby_interpolation(self):
        self.assertFlags('INJ-SQL-INTERP', 'User.where("name = \'#{params[:name]}\'")', 'a.rb')

    def test_sql_ruby_placeholder_clean(self):
        self.assertClean('INJ-SQL-INTERP', 'User.where("name = ?", params[:name])', 'a.rb')

    def test_sql_csharp_interpolated_vs_safe_ef(self):
        self.assertFlags('INJ-SQL-INTERP', 'var q = $"SELECT * FROM Users WHERE Id = {id}";', 'C.cs')
        self.assertClean('INJ-SQL-INTERP',
                         'ctx.Users.FromSqlInterpolated($"SELECT * FROM Users WHERE Id = {id}")', 'C.cs')

    def test_sql_php_variable(self):
        self.assertFlags('INJ-SQL-INTERP', '$r = mysqli_query($c, "SELECT * FROM u WHERE id = $id");', 'x.php')

    def test_nosql_request_filter(self):
        self.assertFlags('INJ-NOSQL', 'User.findOne(req.body)', 's.js')

    def test_shell_true(self):
        self.assertFlags('INJ-CMD-SHELL-TRUE', 'subprocess.run("ls " + d, shell=True)', 'a.py')

    def test_subprocess_list_clean(self):
        self.assertClean('INJ-CMD-SHELL-TRUE', 'subprocess.run(["ls", d])', 'a.py')

    def test_node_exec_template(self):
        self.assertFlags('INJ-CMD-NODE-EXEC', 'exec(`convert ${req.query.f} out.png`)', 's.js')

    def test_go_shell(self):
        self.assertFlags('INJ-CMD-GO-SHELL', 'exec.Command("sh", "-c", userCmd)', 'm.go')

    def test_php_shell(self):
        self.assertFlags('INJ-CMD-PHP', 'system("ping " . $host);', 'x.php')

    def test_ruby_shell(self):
        self.assertFlags('INJ-CMD-RUBY', 'system("convert #{params[:f]}")', 'a.rb')

    def test_eval(self):
        self.assertFlags('INJ-CODE-EVAL', 'result = eval(expr)', 'a.py')

    def test_eval_lookalikes_clean(self):
        for code in ('model.evaluate()', 'def evaluate(x): pass', 'literal_eval(s)'):
            self.assertClean('INJ-CODE-EVAL', code, 'a.py')

    def test_ssti(self):
        self.assertFlags('INJ-SSTI', 'return render_template_string(request.args["t"])', 'a.py')

    def test_ssti_definition_clean(self):
        self.assertClean('INJ-SSTI', 'def render_template_string(source, **ctx):', 'a.py')

    def test_xxe(self):
        self.assertFlags('INJ-XXE', 'parser = etree.XMLParser(resolve_entities=True)', 'a.py')


class XssTest(RuleCase):
    def test_inner_html(self):
        self.assertFlags('XSS-DOM-SINK', 'el.innerHTML = userInput;', 'a.js')

    def test_inner_html_clear_clean(self):
        self.assertClean('XSS-DOM-SINK', 'el.innerHTML = "";', 'a.js')

    def test_inner_html_comparison_clean(self):
        # Reading/comparing innerHTML is not a write sink.
        self.assertClean('XSS-DOM-SINK', 'if (el.innerHTML == expected) { ok(); }', 'a.js')
        self.assertClean('XSS-DOM-SINK', 'if (el.innerHTML === "") { ok(); }', 'a.js')

    def test_framework_raw(self):
        self.assertFlags('XSS-FRAMEWORK-RAW', '<div dangerouslySetInnerHTML={{__html: b}} />', 'a.tsx')
        self.assertFlags('XSS-FRAMEWORK-RAW', '<div v-html="body"></div>', 'a.vue')

    def test_template_safe_filter(self):
        self.assertFlags('XSS-TEMPLATE-RAW', '{{ comment|safe }}', 'page.html')

    def test_reflected(self):
        self.assertFlags('XSS-REFLECTED', 'res.send(req.query.name);', 'a.js')
        self.assertFlags('XSS-REFLECTED', 'echo $_GET["name"];', 'x.php')


class AccessControlTest(RuleCase):
    def test_path_traversal(self):
        self.assertFlags('BAC-PATH-TRAVERSAL', 'data = open(request.args["file"]).read()', 'a.py')

    def test_ssrf(self):
        self.assertFlags('BAC-SSRF', 'r = requests.get(request.args["url"])', 'a.py')

    def test_open_redirect(self):
        self.assertFlags('BAC-OPEN-REDIRECT', 'return redirect(request.args.get("next"))', 'a.py')

    def test_redirect_lookalike_clean(self):
        self.assertClean('BAC-OPEN-REDIRECT', 'raise FormDataRoutingRedirect(request)', 'a.py')

    def test_mass_assignment(self):
        self.assertFlags('BAC-MASS-ASSIGN', 'User.create(req.body)', 'a.js')
        self.assertFlags('BAC-PERMIT-ALL', 'params.permit!', 'a.rb')

    def test_csrf_disabled(self):
        self.assertFlags('BAC-CSRF-DISABLED', '@csrf_exempt', 'views.py')
        self.assertFlags('BAC-CSRF-DISABLED', 'http.csrf().disable();', 'Sec.java')

    def test_file_include(self):
        self.assertFlags('BAC-FILE-INCLUDE', 'include($_GET["page"]);', 'x.php')


class MisconfigTest(RuleCase):
    def test_debug(self):
        self.assertFlags('CFG-DEBUG', 'DEBUG = True', 'settings.py')
        self.assertClean('CFG-DEBUG', 'DEBUG = False', 'settings.py')

    def test_cors_any_origin(self):
        self.assertFlags('CFG-CORS-ANY', 'app.use(cors({ origin: "*", credentials: true }));', 'a.js')
        self.assertFlags('CFG-CORS-ANY', 'CORS_ALLOW_ALL_ORIGINS = True', 'settings.py')

    def test_cors_exact_origin_clean(self):
        self.assertClean('CFG-CORS-ANY', 'app.use(cors({ origin: "https://app.example.com" }));', 'a.js')

    def test_error_leak(self):
        self.assertFlags('CFG-ERROR-LEAK', 'res.status(500).json({ error: err.stack });', 'a.js')

    def test_cookie_flags(self):
        self.assertFlags('CFG-COOKIE-FLAGS', 'SESSION_COOKIE_SECURE = False', 'settings.py')


class SupplyChainTest(RuleCase):
    def test_pipe_to_shell(self):
        self.assertFlags('SUP-PIPE-TO-SHELL', 'curl -sSL https://x.io/i.sh | sudo bash', 'install.sh')

    def test_unpinned_dependency(self):
        self.assertFlags('SUP-UNPINNED-DEP', '{"dependencies": {"left-pad": "*"}}', 'package.json')
        self.assertClean('SUP-UNPINNED-DEP', '{"dependencies": {"react": "^18.2.0"}}', 'package.json')

    def test_action_pinning(self):
        self.assertFlags('SUP-ACTION-UNPINNED', '  - uses: some-org/deploy@v2', 'ci.yml')
        self.assertClean('SUP-ACTION-UNPINNED', '  - uses: actions/checkout@v4', 'ci.yml')
        self.assertClean('SUP-ACTION-UNPINNED',
                         '  - uses: o/t@0123456789abcdef0123456789abcdef01234567', 'ci.yml')

    def test_trust_remote_code(self):
        self.assertFlags('SUP-TRUST-REMOTE-CODE',
                         'AutoModel.from_pretrained("x/y", trust_remote_code=True)', 'a.py')


class CryptoTest(RuleCase):
    def test_weak_hash(self):
        self.assertFlags('CRY-WEAK-HASH', 'h = hashlib.md5(data)', 'a.py')
        self.assertFlags('CRY-WEAK-HASH', 'MessageDigest.getInstance("SHA-1")', 'A.java')

    def test_weak_hash_non_security_clean(self):
        self.assertClean('CRY-WEAK-HASH', 'h = hashlib.md5(data, usedforsecurity=False)', 'a.py')

    def test_password_fast_hash(self):
        self.assertFlags('CRY-PASSWORD-FAST-HASH', 'stored = sha256(password.encode())', 'a.py')

    def test_weak_cipher(self):
        self.assertFlags('CRY-WEAK-CIPHER', 'Cipher.getInstance("AES/ECB/PKCS5Padding")', 'A.java')
        self.assertFlags('CRY-WEAK-CIPHER', 'c = AES.new(k, AES.MODE_ECB)', 'a.py')
        self.assertClean('CRY-WEAK-CIPHER', 'Cipher.getInstance("AES/GCM/NoPadding")', 'A.java')

    def test_insecure_random(self):
        self.assertFlags('CRY-INSECURE-RANDOM', 'reset_token = random.randint(0, 999999)', 'a.py')
        self.assertFlags('CRY-INSECURE-RANDOM', 'const token = Math.random().toString(36);', 'a.js')

    def test_secure_random_clean(self):
        self.assertClean('CRY-INSECURE-RANDOM', 'token = secrets.token_urlsafe(32)', 'a.py')

    def test_tls_verify_off(self):
        self.assertFlags('CRY-TLS-VERIFY-OFF', 'requests.get(u, verify=False)', 'a.py')
        self.assertFlags('CRY-TLS-VERIFY-OFF', 'new https.Agent({ rejectUnauthorized: false })', 'a.js')
        self.assertFlags('CRY-TLS-VERIFY-OFF', 'cfg := &tls.Config{InsecureSkipVerify: true}', 'm.go')

    def test_private_key(self):
        self.assertFlags('CRY-PRIVATE-KEY', '-----BEGIN RSA ' + 'PRIVATE KEY-----', 'key.pem')


class AuthTest(RuleCase):
    def test_cloud_token(self):
        self.assertFlags('AUTH-CLOUD-TOKEN', 'k = "AKIAIOSFODNN7EXAMPLE"', 'a.py')
        self.assertFlags('AUTH-CLOUD-TOKEN', 't = "ghp_' + 'a' * 36 + '"', 'a.py')

    def test_hardcoded_secret(self):
        self.assertFlags('AUTH-HARDCODED-SECRET', 'password = "hunter2hunter2"', 'a.py')

    def test_placeholder_and_env_secret_clean(self):
        for code in ('SECRET_KEY = "changeme-in-prod"',
                     'password = os.environ["DB_PASSWORD"]',
                     'api_key = "${API_KEY}"',
                     'password = "your-password-here"'):
            self.assertClean('AUTH-HARDCODED-SECRET', code, 'a.py')

    def test_jwt_none_and_decode(self):
        self.assertFlags('AUTH-JWT-NONE', 'jwt.decode(t, options={"verify_signature": False})', 'a.py')
        self.assertFlags('AUTH-JWT-DECODE', 'const p = jwt.decode(token);', 'a.js')

    def test_timing_compare(self):
        self.assertFlags('AUTH-TIMING-COMPARE', 'if signature == expected:', 'a.py')
        self.assertClean('AUTH-TIMING-COMPARE', 'if token is None:', 'a.py')
        self.assertClean('AUTH-TIMING-COMPARE', 'if token == None:', 'a.py')


class IntegrityTest(RuleCase):
    def test_pickle_and_yaml(self):
        self.assertFlags('INT-PY-DESERIALIZE', 'obj = pickle.loads(blob)', 'a.py')
        self.assertFlags('INT-PY-DESERIALIZE', 'cfg = yaml.load(s)', 'a.py')

    def test_safe_yaml_clean(self):
        self.assertClean('INT-PY-DESERIALIZE', 'cfg = yaml.load(s, Loader=yaml.SafeLoader)', 'a.py')
        self.assertClean('INT-PY-DESERIALIZE', 'cfg = yaml.safe_load(s)', 'a.py')

    def test_torch_load(self):
        self.assertFlags('INT-TORCH-LOAD', 'm = torch.load("c.pt")', 'a.py')
        self.assertClean('INT-TORCH-LOAD', 'm = torch.load("c.pt", weights_only=True)', 'a.py')

    def test_php_unserialize(self):
        self.assertFlags('INT-PHP-UNSERIALIZE', '$o = unserialize($_COOKIE["d"]);', 'x.php')
        self.assertClean('INT-PHP-UNSERIALIZE',
                         '$o = unserialize($d, ["allowed_classes" => false]);', 'x.php')

    def test_dotnet_and_java(self):
        self.assertFlags('INT-DOTNET-DESERIALIZE', 'var f = new BinaryFormatter();', 'C.cs')
        self.assertFlags('INT-JVM-DESERIALIZE', 'new ObjectInputStream(in)', 'A.java')

    def test_missing_sri(self):
        self.assertFlags('INT-NO-SRI', '<script src="https://cdn.x.com/lib.js"></script>', 'i.html')
        self.assertClean('INT-NO-SRI',
                         '<script src="https://cdn.x.com/lib.js" integrity="sha384-abc"></script>',
                         'i.html')


class LoggingAndExceptionsTest(RuleCase):
    def test_secret_in_log(self):
        self.assertFlags('LOG-SECRET', 'logger.info(f"login {user} password={password}")', 'a.py')

    def test_python_swallow(self):
        self.assertFlags('EXC-PY-SWALLOW', 'try:\n    x()\nexcept Exception:\n    pass\n', 'a.py')

    def test_python_specific_handler_clean(self):
        self.assertClean('EXC-PY-SWALLOW',
                         'try:\n    x()\nexcept KeyError:\n    log.warning("missing")\n', 'a.py')

    def test_fail_open(self):
        code = 'def ok(u):\n    try:\n        return u.is_admin()\n    except Exception:\n        return True\n'
        self.assertFlags('EXC-FAIL-OPEN', code, 'a.py')

    def test_fail_closed_clean(self):
        code = 'def ok(u):\n    try:\n        return u.is_admin()\n    except Exception:\n        return False\n'
        self.assertClean('EXC-FAIL-OPEN', code, 'a.py')

    def test_empty_catch_and_go(self):
        self.assertFlags('EXC-EMPTY-CATCH', 'try { a(); } catch (e) {}', 'a.js')
        self.assertFlags('EXC-GO-EMPTY-ERR', 'if err != nil {\n}', 'm.go')


class LlmTest(RuleCase):
    def test_system_prompt_interpolation(self):
        code = 'msgs = [{"role": "system", "content": f"You help {user.name}"}]'
        self.assertFlags('LLM-SYSTEM-PROMPT-INTERP', code, 'a.py')
        self.assertClean('LLM-SYSTEM-PROMPT-INTERP',
                         'msgs = [{"role": "system", "content": SYSTEM_PROMPT}]', 'a.py')

    def test_output_to_sink(self):
        self.assertFlags('LLM-OUTPUT-EXEC', 'eval(completion.choices[0].message.content)', 'a.js')

    def test_dangerous_flag(self):
        self.assertFlags('LLM-DANGEROUS-FLAG', 'agent = make(llm, allow_dangerous_code=True)', 'a.py')


class MemoryTest(RuleCase):
    def test_gets_and_strcpy(self):
        self.assertFlags('MEM-GETS', 'gets(buf);', 'm.c')
        self.assertFlags('MEM-UNBOUNDED-COPY', 'strcpy(dst, src);', 'm.c')
        self.assertClean('MEM-GETS', 'fgets(buf, sizeof buf, stdin);', 'm.c')


class ScopeTest(RuleCase):
    def test_comment_lines_skipped(self):
        self.assertClean('INJ-CMD-OS-SYSTEM', '# os.system("rm -rf /")', 'a.py')
        self.assertClean('INJ-CODE-EVAL', '// eval(x)', 'a.js')

    def test_secrets_flagged_even_in_comments(self):
        self.assertFlags('AUTH-CLOUD-TOKEN', '# key: AKIAIOSFODNN7EXAMPLE', 'a.py')

    def test_language_scoping(self):
        # A Python rule must not fire on a JS file and vice versa.
        self.assertClean('INJ-CMD-SHELL-TRUE', 'subprocess.run(x, shell=True)', 'a.js')
        self.assertClean('XSS-DOM-SINK', 'el.innerHTML = x', 'a.py')

    def test_test_files_marked(self):
        lines = [(1, 'cur.execute(f"SELECT 1 WHERE x={x}")')]
        hits = scan.scan_lines('tests/test_db.py', lines, '.py', scan.RULES)
        self.assertTrue(hits and all(h.in_test for h in hits))

    def test_test_file_hits_downgraded_one_tier(self):
        lines = [(1, 'cur.execute(f"SELECT 1 WHERE x={x}")')]
        hit = scan.scan_lines('tests/test_db.py', lines, '.py', scan.RULES)[0]
        self.assertEqual(hit.confidence, 'medium')  # rule is 'high'
        src = scan.scan_lines('app/db.py', lines, '.py', scan.RULES)[0]
        self.assertEqual(src.confidence, 'high')

    def test_live_credentials_keep_confidence_in_tests(self):
        lines = [(1, 'k = "AKIAIOSFODNN7EXAMPLE"')]
        hit = scan.scan_lines('test/fixtures.ts', lines, '.ts', scan.RULES)[0]
        self.assertEqual((hit.rule, hit.confidence), ('AUTH-CLOUD-TOKEN', 'high'))


class DiffModeTest(unittest.TestCase):
    DIFF = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -10,3 +10,4 @@ def x():\n"
        " ctx = 1\n"
        "-cur.execute(\"SELECT 1 WHERE id = %s\", (uid,))\n"
        "+cur.execute(f\"SELECT 1 WHERE id = {uid}\")\n"
        " more = 2\n"
        "@@ -40,2 +41,4 @@\n"
        " a = 1\n"
        "+try:\n"
        "+    x()\n"
        "diff --git a/old.py b/old.py\n"
        "deleted file mode 100644\n"
        "--- a/old.py\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-os.system(x)\n"
    )

    def test_added_line_numbers_track_new_file(self):
        added = scan.parse_added_lines(self.DIFF)
        self.assertEqual(added['app.py'][0], (11, 'cur.execute(f"SELECT 1 WHERE id = {uid}")'))
        self.assertEqual([n for n, _ in added['app.py']], [11, 42, 43])

    def test_removed_and_deleted_code_not_scanned(self):
        _, hits = scan.scan_diff(self.DIFF, scan.RULES)
        rules = {h.rule for h in hits}
        self.assertIn('INJ-SQL-FSTRING', rules)
        self.assertNotIn('INJ-CMD-OS-SYSTEM', rules)  # only in a deleted file
        self.assertEqual({h.file for h in hits}, {'app.py'})

    def test_hunks_not_glued_for_multiline_rules(self):
        diff = (
            "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
            "@@ -1,1 +1,2 @@\n x\n+except Exception:\n"
            "@@ -50,1 +51,2 @@\n y\n+    pass\n"
        )
        _, hits = scan.scan_diff(diff, scan.RULES)
        self.assertNotIn('EXC-PY-SWALLOW', {h.rule for h in hits})


class ReportingTest(unittest.TestCase):
    def _hits(self):
        lines = [(i, 'cur.execute(f"SELECT {x}")') for i in range(1, 8)]
        return scan.scan_lines('a.py', lines, '.py', scan.RULES)

    def test_cap_per_rule(self):
        shown, dropped = scan.filter_and_cap(self._hits(), 'low', 3)
        self.assertEqual(sum(1 for h in shown if h.rule == 'INJ-SQL-FSTRING'), 3)
        self.assertEqual(dropped['INJ-SQL-FSTRING'], 4)

    def test_min_confidence(self):
        lines = [(1, 'strcpy(a, b);'), (2, 'gets(buf);')]
        hits = scan.scan_lines('m.c', lines, '.c', scan.RULES)
        shown, _ = scan.filter_and_cap(hits, 'high', 0)
        self.assertEqual({h.rule for h in shown}, {'MEM-GETS'})

    def test_token_supersedes_generic_secret(self):
        lines = [(1, 'API_KEY = "sk_' + 'live_' + '51HabcdefghijklmnopqrstuvWXYZ"')]
        hits = scan.scan_lines('a.py', lines, '.py', scan.RULES)
        shown, _ = scan.filter_and_cap(hits, 'low', 0)
        self.assertEqual([h.rule for h in shown], ['AUTH-CLOUD-TOKEN'])

    def test_text_report_is_plain_and_complete(self):
        buf = io.StringIO()
        shown, dropped = scan.filter_and_cap(self._hits(), 'low', 2)
        scan.print_report(1, shown, dropped, 'test', out=buf)
        text = buf.getvalue()
        self.assertIn('A05:2025 Injection', text)
        self.assertIn('CWE-89', text)
        self.assertIn('+5 more', text)
        self.assertTrue(text.isascii(), 'report must be ASCII so every console can show it')


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, 'app.py'), 'w') as f:
            f.write('import subprocess\nsubprocess.run(cmd, shell=True)\n')
        os.makedirs(os.path.join(self.tmp, 'node_modules', 'x'))
        with open(os.path.join(self.tmp, 'node_modules', 'x', 'i.js'), 'w') as f:
            f.write('eval(x)\n')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *args, stdin=None):
        return subprocess.run([sys.executable, _SCRIPT, *args], input=stdin,
                              capture_output=True)

    def test_json_output_and_excluded_dirs(self):
        r = self.run_cli(self.tmp, '--json')
        self.assertEqual(r.returncode, 0, r.stderr.decode(errors='replace'))
        data = json.loads(r.stdout.decode('utf-8'))
        rules = {c['rule'] for c in data['candidates']}
        self.assertIn('INJ-CMD-SHELL-TRUE', rules)
        self.assertNotIn('INJ-CODE-EVAL', rules, 'node_modules must be skipped')
        self.assertTrue(all('owasp' in c and 'cwe' in c for c in data['candidates']))

    def test_fail_on_exit_code(self):
        self.assertEqual(self.run_cli(self.tmp, '--fail-on', 'high').returncode, 2)
        clean = tempfile.mkdtemp()
        try:
            with open(os.path.join(clean, 'ok.py'), 'w') as f:
                f.write('print("hi")\n')
            self.assertEqual(self.run_cli(clean, '--fail-on', 'low').returncode, 0)
        finally:
            shutil.rmtree(clean, ignore_errors=True)

    def test_diff_from_stdin(self):
        diff = b"diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -0,0 +1 @@\n+os.system(x)\n"
        r = self.run_cli('--diff', '--json', stdin=diff)
        data = json.loads(r.stdout.decode('utf-8'))
        self.assertEqual([c['line'] for c in data['candidates']], [1])

    def test_list_rules(self):
        r = self.run_cli('--list-rules')
        self.assertEqual(r.returncode, 0)
        self.assertIn(b'A01:2025 Broken Access Control', r.stdout)

    def test_missing_path_errors(self):
        self.assertEqual(self.run_cli(os.path.join(self.tmp, 'nope')).returncode, 1)

    def test_ascii_console_does_not_crash(self):
        r = subprocess.run([sys.executable, _SCRIPT, self.tmp], capture_output=True,
                           env={**os.environ, 'PYTHONIOENCODING': 'ascii'})
        self.assertEqual(r.returncode, 0, r.stderr.decode(errors='replace'))

    def test_main_in_process(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = scan.main([self.tmp, '--min-confidence', 'high'])
        self.assertEqual(rc, 0)
        self.assertIn('INJ-CMD-SHELL-TRUE', buf.getvalue())


if __name__ == '__main__':
    unittest.main()
