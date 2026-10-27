"""Reject incomplete pytest reports and require real Windows Shell coverage."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

NATIVE_CLASS = 'tests.windows.test_shortcut'
NATIVE_NAME = 'test_windows_shortcut_launches_real_window_without_console_from_unicode_path'


@dataclass(frozen=True)
class Results:
    passed: int
    failed: int
    errors: int
    skipped: int
    native_windows: int
    problems: tuple[str, ...]


def inspect_report(path: Path | str, platform: str) -> Results:
    root = ET.parse(path).getroot()
    cases = list(root.iter('testcase'))
    failed = sum(case.find('failure') is not None for case in cases)
    errors = sum(case.find('error') is not None for case in cases)
    skipped = [case for case in cases if case.find('skipped') is not None]
    native = [case for case in cases if case.get('classname') == NATIVE_CLASS and case.get('name') == NATIVE_NAME]
    native_passed = sum(all(case.find(tag) is None for tag in ('failure', 'error', 'skipped')) for case in native)
    problems = []
    if not cases:
        problems.append('No test cases in the pytest report.')
    if failed or errors:
        problems.append(f'Test failures: {failed}; errors: {errors}.')
    if skipped:
        problems.append('Skipped tests are not allowed: ' + ', '.join(
            f'{case.get("classname")}::{case.get("name")}' for case in skipped))
    if platform == 'Windows' and (len(native) != 1 or native_passed != 1):
        problems.append('The real Windows .lnk/pythonw integration test must be present and pass.')
    if platform != 'Windows' and native:
        problems.append('Native Windows integration must run in the Windows job, not this platform suite.')
    return Results(len(cases) - failed - errors - len(skipped), failed, errors,
                   len(skipped), native_passed, tuple(problems))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--platform', required=True, choices=('Windows', 'Linux'))
    args = parser.parse_args(argv)
    actual = 'Windows' if sys.platform == 'win32' else 'Linux' if sys.platform.startswith('linux') else sys.platform
    if actual != args.platform:
        print(f'Runner platform mismatch: expected {args.platform}, got {actual}.', file=sys.stderr)
        return 1
    try:
        result = inspect_report(args.report, args.platform)
    except (OSError, ET.ParseError) as exc:
        print(f'Cannot verify pytest results: {exc}', file=sys.stderr)
        return 1
    summary = (f'{args.platform}: {result.passed} passed, {result.failed} failed, '
               f'{result.errors} errors, {result.skipped} skipped; '
               f'native Windows integration passed: {result.native_windows}.')
    print(summary)
    for problem in result.problems:
        print(problem, file=sys.stderr)
    if destination := os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(destination).open('a', encoding='utf-8') as stream:
            stream.write('## Test verification\n\n' + summary + '\n\n')
            if args.platform != 'Windows':
                stream.write('Native .lnk/pythonw coverage is executed in the Windows job.\n\n')
            for problem in result.problems:
                stream.write('- ' + problem + '\n')
    return 1 if result.problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
