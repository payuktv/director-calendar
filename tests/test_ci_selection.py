"""Focused checks must include affected areas and fail conservatively to full."""
import pytest

from scripts.run_ci_tests import changed_paths, is_version_only, main, select_tests, version_only_paths


def test_sync_change_keeps_related_domains_without_unrelated_theme_rendering():
    paths, reason = select_tests(['director_control/mail_calendar.py'], 'Windows')
    assert 'focused' in reason
    assert {'tests/test_mail_calendar.py', 'tests/test_mail_withdrawal.py', 'tests/test_source_state.py',
            'tests/test_analytics.py', 'tests/windows/test_shortcut.py'} <= set(paths)
    assert 'tests/test_theme.py' not in paths


@pytest.mark.parametrize('path', ['director_control/storage.py', 'director_control/new_module.py',
    'director_control/ui.py', 'pyproject.toml', 'tests/conftest.py', 'tests/helpers.py',
    'scripts/run_ci_tests.py', '.github/workflows/ci.yml', 'packaging/installer.iss',
    'tests/test_removed_file.py'])
def test_broad_unknown_or_removed_changes_use_full_suite(path):
    paths, reason = select_tests([path], 'Windows')
    assert paths == ['tests'] and reason.startswith('full:')


def test_docs_keep_smoke_and_native_windows_coverage():
    paths, reason = select_tests(['README.md', 'docs/RELEASING.md'], 'Windows')
    assert 'focused' in reason and 'tests/test_gui_smoke.py' in paths
    assert 'tests/windows/test_shortcut.py' in paths


def test_changed_test_is_included_and_linux_never_collects_native_windows():
    paths, _ = select_tests(['tests/test_analytics.py', 'tests/windows/test_shortcut.py'], 'Linux')
    assert 'tests/test_analytics.py' in paths and 'tests/windows/test_shortcut.py' not in paths


def test_multiple_areas_are_combined_without_duplicate_test_arguments():
    paths, _ = select_tests(['director_control/mail_calendar.py', 'director_control/source_state.py',
                            'director_control/analytics.py'], 'Windows')
    assert len(paths) == len(set(paths))
    assert 'tests/test_analytics_ui.py' in paths


@pytest.mark.parametrize('base,head', [('', ''), ('main', 'HEAD'), ('a'*40, '--unsafe'), ('a'*40, 'b'*39)])
def test_focused_diff_requires_exact_commit_shas(base, head):
    with pytest.raises(ValueError, match='Full base/head'):
        changed_paths(base, head)


def test_suite_from_environment_is_validated_before_running_any_command(monkeypatch):
    monkeypatch.setenv('TEST_SUITE', 'full; unsafe command')
    with pytest.raises(SystemExit) as error:
        main(['--platform', 'Windows'])
    assert error.value.code == 2


@pytest.mark.parametrize('path,before,after,expected', [
    ('pyproject.toml', '[project]\nversion="0.13.2"\ndependencies=["Qt==1"]',
     '[project]\nversion="0.13.3"\ndependencies=["Qt==1"]', True),
    ('pyproject.toml', '[project]\nversion="0.13.2"\ndependencies=["Qt==1"]',
     '[project]\nversion="0.13.3"\ndependencies=["Qt==2"]', False),
    ('pyproject.toml', '[project]\nversion="0.13.2"', '[project]\nname="new"', False),
    ('director_control/__init__.py', '__version__="0.13.2"', '__version__="0.13.3"', True),
    ('director_control/__init__.py', '__version__="0.13.2"', '__version__="0.13.3"\nimport os', False),
    ('director_control/__init__.py', '__version__="0.13.2"', '__version__="0.13.3"\n__version__="1.0.0"', False),
    ('director_control/__init__.py', '__version__="0.13.2"', '__version__=get_version()', False),
    ('director_control/__init__.py', '__version__="0.13.2"', '__version__="custom"', False),
    ('director_control/__init__.py', '__version__="0.13.2"', 'invalid python !', False),
])
def test_version_exemption_requires_unchanged_code_and_metadata(path, before, after, expected):
    assert is_version_only(path, before, after) is expected


def test_version_only_release_bump_keeps_affected_area_selection():
    paths, reason = select_tests(['director_control/mail_calendar.py', 'pyproject.toml',
                                 'director_control/__init__.py'], 'Windows',
                                version_only={'pyproject.toml', 'director_control/__init__.py'})
    assert reason.startswith('focused:') and 'tests/test_mail_calendar.py' in paths
    assert 'tests/test_theme.py' not in paths


def test_version_detection_reads_exact_diff_commits_and_falls_back_on_missing_blob(monkeypatch):
    import subprocess

    calls = []

    def git_output(args, **kwargs):
        calls.append(args)
        if args[-1].endswith(':pyproject.toml'):
            raise subprocess.CalledProcessError(1, args)
        return ('__version__="0.13.2"' if args[-1].startswith('a'*40) else '__version__="0.13.3"').encode()

    monkeypatch.setattr(subprocess, 'check_output', git_output)
    assert version_only_paths(['pyproject.toml', 'director_control/__init__.py'], 'a'*40, 'b'*40) == {
        'director_control/__init__.py'}
    assert ['git', 'show', 'a'*40+':director_control/__init__.py'] in calls
    assert ['git', 'show', 'b'*40+':director_control/__init__.py'] in calls
