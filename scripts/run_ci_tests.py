"""Focused PR checks with a conservative full-suite fallback; full release checks."""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
SMOKE = {'test_gui_smoke', 'test_storage', 'test_runtime_services'}
SYNC = {'test_mail_calendar', 'test_mail_collection', 'test_mail_only', 'test_mail_withdrawal',
        'test_mail_withdrawal_ui', 'test_source_state', 'test_source_state_ui', 'test_credentials',
        'test_edit_conflicts', 'test_freeze_readiness', 'test_analytics', 'test_analytics_ui',
        'test_baseline_rules', 'test_history', 'test_history_ui', 'test_focused_day'}
ANALYTICS = {'test_analytics', 'test_analytics_ui', 'test_baseline_rules', 'test_source_state', 'test_source_state_ui'}
HISTORY = {'test_history', 'test_history_ui', 'test_source_state', 'test_source_state_ui'}
CALENDAR = {'test_calendar_view', 'test_context_menu', 'test_focused_day', 'test_schedule_layers',
            'test_theme', 'test_source_state_ui', 'test_local_event_ui'}
AREAS = {
    **{f'director_control/{name}.py': SYNC for name in ('mail_calendar', 'mail_ui', 'credentials', 'source_state')},
    **{f'director_control/{name}.py': ANALYTICS for name in ('analytics', 'analytics_ui')},
    'director_control/provenance.py': ANALYTICS | {'test_work_origin', 'test_focused_day', 'test_schedule_layers'},
    **{f'director_control/{name}.py': HISTORY for name in ('history', 'history_ui')},
    **{f'director_control/{name}.py': CALENDAR for name in ('calendar_view', 'schedule', 'inspector', 'status_menu')},
    'director_control/local_event_dialog.py': {'test_local_event_ui', 'test_local_events', 'test_edit_conflicts', 'test_date_pickers'},
    'director_control/theme.py': {'test_theme', 'test_date_pickers', 'test_local_event_ui', 'test_calendar_view'},
    'director_control/date_picker.py': {'test_date_pickers', 'test_theme', 'test_input_wheel', 'test_local_event_ui'},
    'director_control/mini_calendar.py': {'test_date_pickers', 'test_theme', 'test_calendar_view'},
    'director_control/input_wheel.py': {'test_input_wheel', 'test_date_pickers', 'test_local_event_ui'},
    'director_control/diagnostics.py': {'test_diagnostics', 'test_desktop', 'test_gui_smoke'},
    'director_control/diagnostics_ui.py': {'test_diagnostics', 'test_gui_smoke'},
    'scripts/release.py': {'test_release'},
    'scripts/verify_test_results.py': {'test_ci_results'},
}


def select_tests(changed, platform, root=ROOT, *, version_only=frozenset()):
    """Unknown/runtime-wide changes deliberately run everything on the PR OS."""
    if platform not in {'Windows', 'Linux'}:
        raise ValueError('Unsupported platform')
    selected = {'tests/'+name+'.py' for name in SMOKE}
    if platform == 'Windows':
        selected.add('tests/windows/test_shortcut.py')
    for raw in changed:
        path = raw.replace('\\', '/')
        if path in version_only and path in {'pyproject.toml', 'director_control/__init__.py'}:
            continue
        if path in AREAS:
            selected.update('tests/'+name+'.py' for name in AREAS[path])
        elif path.startswith(('docs/', 'releases/')) or path in {'README.md', '.gitignore'}:
            continue
        elif (path.startswith('tests/test_') or path.startswith('tests/windows/test_')) and path.endswith('.py'):
            if not (root/path).is_file():
                return ['tests'], 'full: removed or unavailable test module'
            if platform == 'Windows' or not path.startswith('tests/windows/'):
                selected.add(path)
        else:
            # Includes schema/storage, application entry points, packaging,
            # dependencies, test fixtures, CI itself and newly introduced modules.
            return ['tests'], 'full: broad or unmapped change'
    if any(not (root/path).is_file() for path in selected):
        raise ValueError('The focused test map references a missing test module')
    return sorted(selected), 'focused: smoke and affected areas'


def is_version_only(path, before, after):
    """Recognize a plain version bump without hiding metadata or code changes."""
    try:
        if path == 'pyproject.toml':
            old, new = tomllib.loads(before), tomllib.loads(after)
            versions = (old['project'].pop('version'), new['project'].pop('version'))
        elif path == 'director_control/__init__.py':
            trees = [ast.parse(text) for text in (before, after)]
            versions = []
            for tree in trees:
                assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                               and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                               and node.targets[0].id == '__version__']
                if len(assignments) != 1 or not isinstance(assignments[0].value, ast.Constant):
                    return False
                versions.append(assignments[0].value.value)
                tree.body.remove(assignments[0])
            old, new = (ast.dump(tree) for tree in trees)
        else:
            return False
        return old == new and all(isinstance(version, str) and re.fullmatch(r'\d+\.\d+\.\d+', version)
                                  for version in versions)
    except (KeyError, TypeError, ValueError, SyntaxError):
        return False


def version_only_paths(changed, base, head):
    if not all(re.fullmatch('[0-9a-f]{40}', value or '') for value in (base, head)):
        raise ValueError('Full base/head commit SHAs are required for focused PR selection')
    result = set()
    for path in set(changed) & {'pyproject.toml', 'director_control/__init__.py'}:
        try:
            before, after = (subprocess.check_output(['git', 'show', f'{sha}:{path}'], cwd=ROOT).decode('utf-8')
                             for sha in (base, head))
        except (subprocess.CalledProcessError, UnicodeError):
            continue  # Any uncertainty retains the broad-change fallback.
        if is_version_only(path, before, after):
            result.add(path)
    return result


def changed_paths(base, head):
    if not all(re.fullmatch('[0-9a-f]{40}', value or '') for value in (base, head)):
        raise ValueError('Full base/head commit SHAs are required for focused PR selection')
    output = subprocess.check_output(['git', 'diff', '--name-only', '--no-renames', '-z', base, head, '--'], cwd=ROOT)
    return [path for path in output.decode('utf-8').split('\0') if path]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=('full', 'focused'), default=os.environ.get('TEST_SUITE', 'full'))
    parser.add_argument('--platform', choices=('Windows', 'Linux'), required=True)
    parser.add_argument('--report', default='pytest-results.xml')
    args = parser.parse_args(argv)
    if args.suite not in {'full', 'focused'}:
        parser.error('Invalid TEST_SUITE value')
    actual = 'Windows' if sys.platform == 'win32' else 'Linux' if sys.platform.startswith('linux') else sys.platform
    if actual != args.platform:
        raise ValueError('Runner platform mismatch')
    if args.suite == 'full':
        paths, reason = ['tests'], 'full: release or explicit manual run'
    else:
        base, head = os.environ.get('PR_BASE_SHA'), os.environ.get('PR_HEAD_SHA')
        changed = changed_paths(base, head)
        paths, reason = select_tests(changed, args.platform, version_only=version_only_paths(changed, base, head))
    plan = {'requested_suite': args.suite, 'reason': reason, 'platform': args.platform, 'paths': paths}
    (ROOT/'ci-test-plan.json').write_text(json.dumps(plan, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(plan, indent=2), flush=True)
    if summary := os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(summary).open('a', encoding='utf-8') as stream:
            stream.write('## Test scope\n\n'+reason+'\n\n'+', '.join(paths)+'\n\n')
    return subprocess.run([sys.executable, '-m', 'pytest', '-q', *paths,
                           '--junitxml='+args.report, '--durations=10'], cwd=ROOT).returncode


if __name__ == '__main__':
    raise SystemExit(main())
