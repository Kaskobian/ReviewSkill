#!/usr/bin/env python3
"""Offline tests for dep-audit.py: parsers, CVSS, fix selection, audit flow, CLI.

Network calls are replaced by canned OSV / KEV / NVD responses.
Run: python scripts/test_dep_audit.py
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dep-audit.py')
_spec = importlib.util.spec_from_file_location('dep_audit', _SCRIPT)
assert _spec is not None and _spec.loader is not None
dep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dep)


def names(found):
    return sorted('%s:%s@%s' % t[:3] for t in found)


class ParserTest(unittest.TestCase):

    def test_package_lock_v3(self):
        lock = json.dumps({'lockfileVersion': 3, 'packages': {
            '': {'name': 'app'},
            'node_modules/lodash': {'version': '4.17.15'},
            'node_modules/@scope/pkg': {'version': '1.0.0'},
            'node_modules/a/node_modules/b': {'version': '2.0.0'},
            'node_modules/local': {'link': True},
            'node_modules/g': {'version': '1.0.0', 'resolved': 'git+https://x/y.git'}}})
        self.assertEqual(names(dep.parse_package_lock(lock)),
                         ['npm:@scope/pkg@1.0.0', 'npm:b@2.0.0', 'npm:lodash@4.17.15'])

    def test_package_lock_v1_alias(self):
        lock = json.dumps({'lockfileVersion': 1, 'dependencies': {
            'lodash': {'version': '4.17.15', 'dependencies': {'minimist': {'version': '0.0.8'}}},
            'old': {'version': 'npm:left-pad@1.1.0'}}})
        self.assertEqual(names(dep.parse_package_lock(lock)),
                         ['npm:left-pad@1.1.0', 'npm:lodash@4.17.15', 'npm:minimist@0.0.8'])

    def test_pnpm_and_yarn(self):
        v9 = "lockfileVersion: '9.0'\npackages:\n  lodash@4.17.15:\n    resolution: {}\n  '@types/node@20.1.0':\n    x: 1\n  react-dom@18.2.0(react@18.2.0):\n    x: 1\nsnapshots:\n  lodash@4.17.15: {}\n"
        v5 = "packages:\n  /@babel/core/7.0.0_supports-color@5.5.0:\n    dev: true\n"
        self.assertEqual(names(dep.parse_pnpm_lock(v9)), ['npm:@types/node@20.1.0', 'npm:lodash@4.17.15', 'npm:react-dom@18.2.0'])
        self.assertEqual(names(dep.parse_pnpm_lock(v5)), ['npm:@babel/core@7.0.0'])
        yarn = 'lodash@^4.17.0, lodash@^4.17.15:\n  version "4.17.15"\n\n"app@workspace:.":\n  version: 0.0.0-use.local\n'
        self.assertEqual(names(dep.parse_yarn_lock(yarn)), ['npm:lodash@4.17.15'])

    def test_nuget(self):
        csproj = ('<Project><ItemGroup>'
                  '<PackageReference Include="Newtonsoft.Json" Version="12.0.1" />'
                  '<PackageReference Include="Serilog"><Version>2.10.0</Version></PackageReference>'
                  '<PackageReference Include="Exact" Version="[1.2.3]" />'
                  '<PackageReference Include="Range" Version="[1.0,2.0)" />'
                  '<PackageReference Include="Var" Version="$(V)" /></ItemGroup></Project>')
        self.assertEqual(names(dep.parse_nuget_project(csproj)),
                         ['NuGet:Exact@1.2.3', 'NuGet:Newtonsoft.Json@12.0.1', 'NuGet:Serilog@2.10.0'])
        self.assertEqual(names(dep.parse_nuget_project('<packages><package id="jQuery" version="1.8.0" /></packages>')),
                         ['NuGet:jQuery@1.8.0'])
        lock = json.dumps({'dependencies': {'net8.0': {'A': {'type': 'Direct', 'resolved': '1.0.0'}, 'B': {'type': 'Project'}}}})
        self.assertEqual(names(dep.parse_nuget_lock(lock)), ['NuGet:A@1.0.0'])

    def test_python(self):
        req = 'Django==3.2.0\nrequests>=2.0\nPyYAML==5.3  # pin\nzope.interface === 5.0 \\\n  --hash=sha256:x\n-r b.txt\nuvicorn[standard]==0.20.0 ; python_version>"3"\n'
        self.assertEqual(names(dep.parse_requirements(req)),
                         ['PyPI:django@3.2.0', 'PyPI:pyyaml@5.3', 'PyPI:uvicorn@0.20.0', 'PyPI:zope-interface@5.0'])
        uv = '[[package]]\nname = "app"\nversion = "0.1.0"\nsource = { editable = "." }\n\n[[package]]\nname = "PyYAML"\nversion = "5.3"\n'
        self.assertEqual(names(dep.parse_poetry_uv_lock(uv)), ['PyPI:pyyaml@5.3'])
        self.assertEqual(names(dep.parse_pipfile_lock(json.dumps({'default': {'Django': {'version': '==3.2.0'}}}))), ['PyPI:django@3.2.0'])

    def test_other_ecosystems(self):
        self.assertEqual(names(dep.parse_go_mod('require (\n\tgithub.com/a/b v1.2.3 // indirect\n)\nrequire golang.org/x/text v0.3.5\n')),
                         ['Go:github.com/a/b@v1.2.3', 'Go:golang.org/x/text@v0.3.5'])
        self.assertEqual(names(dep.parse_cargo_lock('[[package]]\nname = "tokio"\nversion = "1.8.0"\nsource = "registry+https://x"\n\n[[package]]\nname = "local"\nversion = "0.1.0"\n')),
                         ['crates.io:tokio@1.8.0'])
        self.assertEqual(names(dep.parse_composer_lock(json.dumps({'packages': [{'name': 'laravel/framework', 'version': 'v8.0.0'}]}))),
                         ['Packagist:laravel/framework@8.0.0'])
        self.assertEqual(names(dep.parse_gemfile_lock('GEM\n  specs:\n    rails (6.0.0)\n      x (= 1)\n    nokogiri (1.10.0-x86_64-linux)\n\nPLATFORMS\n')),
                         ['RubyGems:nokogiri@1.10.0', 'RubyGems:rails@6.0.0'])
        self.assertEqual(names(dep.parse_gradle_lockfile('a.b:c:2.9.8=compileClasspath\nempty=\n')), ['Maven:a.b:c@2.9.8'])

    def test_collect_skips_vendored_and_reports_bad_files(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        os.makedirs(os.path.join(d, 'node_modules', 'x'))
        with open(os.path.join(d, 'node_modules', 'x', 'package-lock.json'), 'w') as f:
            f.write('{"packages": {"node_modules/evil": {"version": "1.0.0"}}}')
        with open(os.path.join(d, 'requirements.txt'), 'w') as f:
            f.write('Django==3.2.0\n')
        with open(os.path.join(d, 'package-lock.json'), 'w') as f:
            f.write('{ broken')
        pkgs, errors = dep.collect([d])
        self.assertEqual([p[:3] for p in pkgs], [('PyPI', 'django', '3.2.0')])
        self.assertEqual(len(errors), 1)
        self.assertIn('package-lock.json', errors[0])


class ScoreTest(unittest.TestCase):

    def test_cvss3_matches_first_calculator(self):
        for v, s in [('CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H', 10.0),
                     ('CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H', 9.8),
                     ('CVSS:3.1/AV:N/AC:L/PR:H/UI:N/S:U/C:H/I:H/A:H', 7.2),
                     ('CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N', 6.1),
                     ('CVSS:3.0/AV:L/AC:H/PR:L/UI:R/S:U/C:L/I:N/A:N', 2.2)]:
            self.assertEqual(dep.cvss3_score(v), s, v)
        self.assertIsNone(dep.cvss3_score('CVSS:4.0/AV:N'))
        self.assertEqual(dep.severity_of(9.0), 'critical')
        self.assertEqual(dep.severity_of(6.9), 'medium')

    def test_fixed_version(self):
        rec = {'affected': [
            {'package': {'ecosystem': 'npm', 'name': 'lodash'}, 'ranges': [{'events': [{'introduced': '0'}, {'fixed': '4.17.21'}]}]},
            {'package': {'ecosystem': 'npm', 'name': 'lodash'}, 'ranges': [{'events': [{'introduced': '3.0.0'}, {'fixed': '3.10.2'}]}]}]}
        self.assertEqual(dep.fixed_for(rec, 'npm', 'lodash', '4.17.15'), '4.17.21')
        self.assertIsNone(dep.fixed_for(rec, 'npm', 'lodash', '4.17.21'))
        self.assertTrue(dep._cmp('1.10.0', '1.9.0') > 0)
        self.assertTrue(dep._cmp('1.0.0', '1.0.0-rc1') > 0)


def fake_request(osv_down=False, kev_down=False):
    vulns = {
        'GHSA-crit': {'id': 'GHSA-crit', 'aliases': ['CVE-2021-0001', 'PYSEC-x'], 'summary': 'Command injection',
                      'severity': [{'type': 'CVSS_V3', 'score': 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H'}],
                      'affected': [{'package': {'ecosystem': 'npm', 'name': 'lodash'}, 'ranges': [{'events': [{'introduced': '0'}, {'fixed': '4.17.21'}]}]}]},
        'PYSEC-x': {'id': 'PYSEC-x', 'aliases': ['GHSA-crit', 'CVE-2021-0001'], 'affected': []},
        'GHSA-kev': {'id': 'GHSA-kev', 'aliases': ['CVE-2021-0002'], 'summary': 'Exploited', 'database_specific': {'severity': 'MODERATE'},
                     'affected': [{'package': {'ecosystem': 'npm', 'name': 'log4js'}, 'ranges': [{'events': [{'fixed': '6.4.0'}]}]}]},
    }
    affected = {'lodash@4.17.15': ['GHSA-crit', 'PYSEC-x'], 'log4js@6.3.0': ['GHSA-kev']}

    def request(url, body=None, headers=None, timeout=30):
        if 'osv.dev' in url:
            if osv_down:
                raise urllib.error.URLError('offline')
            if url.endswith('/querybatch'):
                return {'results': [{'vulns': [{'id': i} for i in affected.get('%s@%s' % (q['package']['name'], q['version']), [])]}
                                    for q in body['queries']]}
            return vulns[url.rsplit('/', 1)[1]]
        if 'cisa.gov' in url:
            if kev_down:
                raise urllib.error.URLError('offline')
            return {'vulnerabilities': [{'cveID': 'CVE-2021-0002'}]}
        if 'nvd.nist.gov' in url:
            return {'vulnerabilities': [{'cve': {'metrics': {'cvssMetricV31': [{'type': 'Primary', 'cvssData': {'version': '3.1', 'baseScore': 8.8}}]}}}]}
        raise AssertionError(url)
    return request


class AuditTest(unittest.TestCase):
    PKGS = [('npm', 'lodash', '4.17.15', 'package-lock.json'), ('npm', 'log4js', '6.3.0', 'package-lock.json'),
            ('npm', 'safe', '1.0.0', 'package-lock.json')]

    def test_findings_merged_scored_and_kev(self):
        with mock.patch.object(dep, '_request', fake_request()):
            findings, notes = dep.audit(self.PKGS, use_nvd=False, nvd_limit=10)
        self.assertEqual(len(findings), 2, 'GHSA and PYSEC aliases merged')
        kev = findings[0]
        self.assertEqual((kev['package'], kev['kev'], kev['severity'], kev['fixed']), ('log4js', True, 'medium', '6.4.0'))
        crit = findings[1]
        self.assertEqual((crit['package'], crit['score'], crit['severity'], crit['fixed'], crit['cves']),
                         ('lodash', 9.8, 'critical', '4.17.21', ['CVE-2021-0001']))
        self.assertEqual(crit['owasp'], 'A03:2025 Software Supply Chain Failures')
        self.assertEqual(notes, [])

    def test_nvd_fills_missing_scores_only(self):
        with mock.patch.object(dep, '_request', fake_request()), mock.patch.object(dep.time, 'sleep'):
            findings, _ = dep.audit(self.PKGS, use_nvd=True, nvd_limit=10)
        kev = next(f for f in findings if f['package'] == 'log4js')
        self.assertEqual((kev['score'], kev['source'], kev['severity']), (8.8, 'NVD CVSS 3.1', 'high'))
        lodash = next(f for f in findings if f['package'] == 'lodash')
        self.assertEqual(lodash['source'], 'OSV CVSS', 'already scored by OSV: NVD not asked')

    def test_kev_outage_is_a_note(self):
        with mock.patch.object(dep, '_request', fake_request(kev_down=True)):
            findings, notes = dep.audit(self.PKGS, use_nvd=False, nvd_limit=10)
        self.assertFalse(any(f['kev'] for f in findings))
        self.assertIn('CISA KEV unavailable', notes[0])


class CliTest(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        with open(os.path.join(self.dir, 'package-lock.json'), 'w') as f:
            json.dump({'lockfileVersion': 3, 'packages': {'node_modules/lodash': {'version': '4.17.15'}}}, f)

    def run_cli(self, *args, request=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(dep, '_request', request or fake_request()), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = dep.main([self.dir, *args])
        return code, out.getvalue(), err.getvalue()

    def test_text_and_fail_on(self):
        code, out, _ = self.run_cli('--fail-on', 'critical')
        self.assertEqual(code, 2)
        self.assertIn('lodash@4.17.15', out)
        self.assertIn('upgrade to 4.17.21', out)
        self.assertEqual(self.run_cli()[0], 0, 'no --fail-on: report only')

    def test_json(self):
        code, out, _ = self.run_cli('--json')
        data = json.loads(out)
        self.assertEqual((data['packages'], len(data['findings'])), (1, 1))

    def test_offline_lists_packages_without_network(self):
        def no_network(*a, **k):
            raise AssertionError('network used')
        code, out, _ = self.run_cli('--offline', request=no_network)
        self.assertEqual(code, 0)
        self.assertIn('lodash@4.17.15', out)

    def test_osv_down_is_an_error_not_a_pass(self):
        code, _, err = self.run_cli(request=fake_request(osv_down=True))
        self.assertEqual(code, 1)
        self.assertIn('NOT checked', err)

    def test_missing_path(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(dep.main([os.path.join(self.dir, 'nope')]), 1)


if __name__ == '__main__':
    unittest.main(verbosity=1)
