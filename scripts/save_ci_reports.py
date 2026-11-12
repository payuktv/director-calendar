"""Keep complete CI reports in logs and a bounded job summary, without artifacts."""
import html
import json
import os
from pathlib import Path


REPORTS = ('ci-test-plan.json', 'pytest-results.xml')
SUMMARY_LIMIT = 900_000  # GitHub allows at most 1 MiB per step summary.


def save_reports(folder, summary=None, emit=print):
    sections = []
    for name in REPORTS:
        path = Path(folder) / name
        if not path.is_file():
            emit(f'CI report unavailable: {name}')
            continue  # The mandatory verification step separately rejects missing JUnit.
        content = path.read_text(encoding='utf-8')
        # JSON keeps each file on one log line: test output cannot inject a new
        # GitHub workflow command. The full report remains downloadable in logs.
        emit(json.dumps({'file': name, 'content': content}, ensure_ascii=True))
        sections.append('<details><summary>' + name + '</summary><pre>'
                        + html.escape(content) + '</pre></details>\n')
    if summary:
        body = ''.join(sections)
        if len(body.encode('utf-8')) > SUMMARY_LIMIT:
            body = 'Detailed CI reports exceed the summary limit; see the complete JSON records in this step log.\n'
        with Path(summary).open('a', encoding='utf-8') as stream:
            stream.write(body)


if __name__ == '__main__':
    save_reports(Path.cwd(), os.environ.get('GITHUB_STEP_SUMMARY'))
