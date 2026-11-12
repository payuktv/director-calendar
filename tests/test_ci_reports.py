import json

from scripts import save_ci_reports as reports


def test_reports_survive_in_logs_and_escape_summary_and_workflow_commands(tmp_path):
    content = '<testcase name="synthetic">\n::error::test output\n</testcase>'
    (tmp_path / 'pytest-results.xml').write_text(content, encoding='utf-8')
    plan = '{"scope":"full"}'
    (tmp_path / 'ci-test-plan.json').write_text(plan, encoding='utf-8')
    logged = []
    summary = tmp_path / 'summary.md'
    reports.save_reports(tmp_path, summary, logged.append)
    assert len(logged) == 2 and all('\n' not in line for line in logged)
    assert {item['file']: item['content'] for item in map(json.loads, logged)} == {
        'pytest-results.xml': content, 'ci-test-plan.json': plan}
    assert '<testcase' not in summary.read_text(encoding='utf-8')
    assert '&lt;testcase' in summary.read_text(encoding='utf-8')


def test_oversized_summary_preserves_the_full_log_report(tmp_path, monkeypatch):
    monkeypatch.setattr(reports, 'SUMMARY_LIMIT', 100)
    content = 'я' * 1000
    (tmp_path / 'pytest-results.xml').write_text(content, encoding='utf-8')
    summary, logged = tmp_path / 'summary.md', []
    reports.save_reports(tmp_path, summary, logged.append)
    assert 'exceed the summary limit' in summary.read_text(encoding='utf-8')
    assert json.loads(logged[-1])['content'] == content


def test_missing_reports_are_identified_without_masking_the_failed_test_step(tmp_path):
    logged = []
    reports.save_reports(tmp_path, emit=logged.append)
    assert logged == ['CI report unavailable: ' + name for name in reports.REPORTS]
