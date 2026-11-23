# Test scope and release gates

During development, run tests for the behavior being changed and its related storage/UI/report paths. Run Ruff F checks before creating the PR. Re-run a passing selection only after relevant changes or a new unresolved concern. Do not run both operating systems after every small edit.

## Pull requests

- One Tests workflow, on Windows, triggered by the PR rather than both push and PR.
- `scripts/run_ci_tests.py` combines fixed smoke checks with an explicit affected-area map and changed test modules. Every Windows run includes the real shortcut integration test.
- Broad changes, storage/schema, runtime entry points, shared fixtures, dependencies, the selector/CI configuration, removed tests and unmapped files select the complete Windows suite. An unknown change cannot silently receive a narrow selection.
- A plain version bump in `pyproject.toml` and `director_control/__init__.py` preserves focused selection only after comparing both commit versions and confirming that all other metadata and Python code are unchanged. Dependency or runtime changes still select the full suite.
- UI changes select the tests for the affected screens. When a translation catalog edit is verified as a change to literal entries, selection includes the language tests. Changing the structure or behavior of the catalog selects the full Windows suite.
- Superseded runs for the same PR are cancelled. Dependency packages are cached. The selected paths, slowest test timings and complete JUnit report are retained in the job log and summary, without Actions artifact storage. Oversized summaries link readers to the full JSON-encoded report in the log.
- Packaging/native lifecycle PRs also run Windows distribution acceptance. Other PRs do not build two installers just to check a source change.

For example, changes to Mail.ru transport select transport, recurrence, withdrawal, cancellation, freeze protection, analytics, history and related UI checks, plus smoke/native coverage. Changes to the main Store deliberately select the full Windows suite because its effects are broad.

## Releases

Release determines the test scope for the final commit on `main`. It resolves the preceding published version to its source commit and examines the entire change between those commits, including earlier merged PRs.

- **Cosmetic release.** If the whole change matches the supported edits to literal palette colors or displayed labels and translations, run smoke tests and the affected checks on both Windows and Linux. Documentation, release notes and numeric version bumps can accompany these edits.
- **Full release.** Changes to logic, data, runtime, dependencies, packaging, test infrastructure or CI select both full suites. A missing or unverifiable baseline or an unrecognized change also selects full testing. The first release containing the CI policy change itself therefore receives full testing.
- **Every release.** Each platform must produce a nonempty report with zero failures, errors and skips. Windows must pass the native shortcut test. After both pass, validate the installer, upgrade from the previous published version, data preservation, backups and recovery. Publish the verified distribution directly from that job.

Running **Tests** manually runs both full suites. Running **Release** manually applies the same release scope selection as an automatic publication.

## Updating the map

When introducing a narrow mapping, include affected consumers as well as direct unit tests, and review the mapping together with the feature. New or uncertain modules can remain unmapped and run the full suite. Update the selector regression tests when changing either the PR map or the criteria for a cosmetic release.

The interpreter is pinned by `.python-version` (3.14.10) for both platform suites and packaging. Distribution acceptance reads Python, Expat and OpenSSL versions inside the frozen executable; publication rejects missing, older or different runtimes. The highest earlier published installer is the upgrade baseline, with complete installed-file hash comparison.

Both platform jobs prepare the Expat 2.10.0 overlay before pytest. This compiles the paired `pyexpat`/`_elementtree` modules from verified upstream sources and runs CPython's XML regression suites. Local native-runtime tests also require this overlay on `PYTHONPATH`; an old parser is a failure, not a skipped test. See README for preparation commands. Distribution acceptance exercises record validation and the actual bundled XML modules, including the fixed empty-subparser case.
