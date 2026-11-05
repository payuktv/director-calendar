# Test scope and release gates

During development, run tests for the behavior being changed and its related storage/UI/report paths. Run Ruff F checks before creating the PR. Re-run a passing selection only after relevant changes or a new unresolved concern. Do not run both operating systems after every small edit.

## Pull requests

- One Tests workflow, on Windows, triggered by the PR rather than both push and PR.
- `scripts/run_ci_tests.py` combines fixed smoke checks with an explicit affected-area map and changed test modules. Every Windows run includes the real shortcut integration test.
- Broad changes, storage/schema, runtime entry points, shared fixtures, dependencies, the selector/CI configuration, removed tests and unmapped files select the complete Windows suite. An unknown change cannot silently receive a narrow selection.
- A plain version bump in `pyproject.toml` and `director_control/__init__.py` preserves focused selection only after comparing both commit versions and confirming that all other metadata and Python code are unchanged. Dependency or runtime changes still select the full suite.
- UI/visual changes select the relevant rendering tests. Isolated calendar transport changes do not run theme rendering tests.
- Superseded runs for the same PR are cancelled. Dependency packages are cached. The selected paths, slowest test timings and JUnit report are retained so performance and coverage can be inspected.
- Packaging/native lifecycle PRs also run Windows distribution acceptance. Other PRs do not build two installers just to check a source change.

For example, changes to Mail.ru transport select transport, recurrence, withdrawal, cancellation, freeze protection, analytics, history and related UI checks, plus smoke/native coverage. Changes to the main Store deliberately select the full Windows suite because its effects are broad.

## Releases

Release explicitly invokes the full Windows and Linux suites on the final main commit. It also builds the Windows distribution and validates installation, previous-version upgrade, preservation of data, backups and recovery. Publication requires all of these jobs to pass. A focused PR report never substitutes for the full release result.

The reusable test workflow defaults to full scope. An explicit manual Tests run also runs both complete platform suites. Main does not separately repeat the same jobs while Release runs them. Linux omits native Windows collection; skips, failures, empty reports and missing native Windows coverage are rejected as before.

## Updating the map

When introducing a narrow mapping, include affected consumers as well as direct unit tests, and review the mapping together with the feature. New or uncertain modules can remain unmapped and run the full suite. Update `tests/test_ci_selection.py` when changing selection policy. This map is a PR feedback optimization, not a promise that unrelated test modules can never expose a regression.
