"""The CI verifier must reject real skipped/failed runs, not relabel them."""
import subprocess
import sys

import pytest

from scripts.verify_test_results import inspect_report, main


@pytest.mark.parametrize('outcome', ['pass', 'skip', 'fail'])
def test_verifier_checks_real_pytest_junit_output(tmp_path, outcome):
    # An isolated pytest project intentionally exercises each report outcome.
    # Its skip is rejected by the verifier; this outer test still executes.
    body = {'pass': 'assert True', 'skip': "pytest.skip('Intentional verifier probe')", 'fail': 'assert False'}[outcome]
    probe = tmp_path / 'test_probe.py'
    probe.write_text('import pytest\n\ndef test_probe():\n    ' + body + '\n', encoding='utf-8')
    report = tmp_path / 'results.xml'
    run = subprocess.run([sys.executable, '-m', 'pytest', '-q', '--junitxml=' + str(report), str(probe)],
                         cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert run.returncode == (1 if outcome == 'fail' else 0), run.stdout + run.stderr
    results = inspect_report(report, 'Linux')
    assert bool(results.problems) is (outcome != 'pass')
    assert results.skipped == (outcome == 'skip')
    assert results.failed == (outcome == 'fail')
    assert results.passed == (outcome == 'pass')


def test_windows_report_cannot_omit_native_shortcut_coverage(tmp_path):
    report = tmp_path / 'portable.xml'
    report.write_text('<testsuites><testsuite><testcase classname="tests.test_storage" name="test_store"/>'
                      '</testsuite></testsuites>', encoding='utf-8')
    assert not inspect_report(report, 'Linux').problems
    result = inspect_report(report, 'Windows')
    assert result.native_windows == 0
    assert any('.lnk/pythonw' in problem for problem in result.problems)


@pytest.mark.parametrize('content', ['', '<testsuites/>'])
def test_missing_or_empty_results_cannot_pass(tmp_path, content, capsys, monkeypatch):
    monkeypatch.delenv('GITHUB_STEP_SUMMARY', raising=False)
    report = tmp_path / 'invalid.xml'
    if content:
        report.write_text(content, encoding='utf-8')
    platform = 'Windows' if sys.platform == 'win32' else 'Linux'
    assert main([str(report), '--platform', platform]) == 1
    assert capsys.readouterr().err
