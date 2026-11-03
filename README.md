# Director Calendar — v0.12.1

A local Windows desktop application for tracking a CEO's schedule, original plan, actual work and change history. Mail.ru is a read-only calendar source; local events and execution records stay on the user's computer.

**Status:** pre-release. **v1.0.0 is reserved for the production release.** The application interface is currently in Russian; the English labels below describe its controls.

## Features

- Day, week, month and agenda views, with separate current schedule, original plan and actual-work layers.
- Read-only Mail.ru CalDAV import, including recurring events and individual exceptions.
- Local planned events and post-factum records for unplanned work; no writes to Mail.ru.
- Manual, one-time daily plan fixation, execution statuses, actual times and comments.
- Daily, weekly and monthly analytics, data-quality indicators and CSV export.
- Full retained change history with search, date/event filters and pagination.
- Light/dark themes, desktop shortcuts and single-instance protection.
- Verified manual/daily backups, update backups and startup recovery for damaged databases.
- Standalone Windows x64 installer and portable ZIP. Python is bundled.

![Calendar, light theme](docs/screenshots/calendar-week.png)
![Calendar, dark theme](docs/screenshots/calendar-week-dark.png)

Screenshots use synthetic data and may show an earlier interface revision. No demo schedule is created on a fresh installation.

## Install on Windows

Target platform: Windows 10/11 x64. Use the installer for normal use; Python, PowerShell and administrator privileges are not required to run the installed application.

1. Open [GitHub Releases](https://github.com/payuktv/director-calendar/releases) and select the intended version, currently **[v0.12.1](https://github.com/payuktv/director-calendar/releases/tag/v0.12.1)**.
2. Read its release notes and known limitations. Versions below v1.0.0 are marked **Pre-release**.
3. Download the installer from **Assets**. Access to this private repository is required. GitHub's automatic source-code archives are for development, not installation.
4. Close any running Director Calendar instance, including older source-based launches.
5. Run `DirectorCalendar-0.12.1-Setup-x64.exe` as your normal Windows user.
6. Open **Director Calendar** from the desktop or Start menu.

Release assets include the installer, portable ZIP, SHA-256 checksums, build/dependency information, distribution acceptance report, upgrade-source record and release manifest. A release is published only after Windows/Linux tests and Windows distribution acceptance pass for the same source commit, and uploaded assets are verified. Releases provide the permanent download channel; temporary Actions artifacts are still retained for **30 days** for CI inspection. Installers are not currently Authenticode-signed.

For portable use, extract the **entire** `DirectorCalendar-0.12.1-portable-x64.zip`. Keep `DirectorCalendar.exe` and `_internal` together. Data still lives in AppData, not beside the executable. Create a shortcut from Settings if needed.

## Update and data locations

Close the application, run the new installer and reopen the existing shortcut. Updates are installed manually; there is no automatic update download.

| Item | Default location |
| --- | --- |
| Installed program | `%LOCALAPPDATA%\Programs\DirectorCalendar` |
| Database, settings and history | `%LOCALAPPDATA%\DirectorControl\director_control.db` |
| Default backups | `%LOCALAPPDATA%\DirectorControl\backups` |
| Preserved emergency-recovery files | `%LOCALAPPDATA%\DirectorControl\recovery` |
| Saved Mail.ru password | Windows Credential Manager, service `DirectorControl.CalDAV` |

Installation, update and uninstallation preserve the separate data directory and saved credentials. Before an existing database is opened by a different application version, a verified `before-update-*.db` backup is required. Failure to create it prevents normal startup. Reopening the same version does not create duplicate version backups.

If you previously set `DIRECTOR_CONTROL_DATA_DIR`, preserve that environment variable when launching the new installation. A custom database location is not discovered automatically. Moving to another Windows account or PC requires entering the Mail.ru application password again; database backups do not contain Windows Vault credentials.

The installer blocks downgrades and installation/removal while a v0.11.0-or-later instance is running. Close earlier versions manually before updating. For a portable update, extract the new package into a separate directory and update the shortcut; do not mix `_internal` directories from different versions.

## Connect Mail.ru

1. Open **Settings → Mail.ru calendar**.
2. Enter the full CalDAV collection URL from your calendar settings and your full email login.
3. Enter a Mail.ru **application password**, locally on your computer. Do not put it in chat, source files or GitHub.
4. Select the display time zone, normally `Europe/Moscow`.
5. Optionally save the password in Windows Credential Manager. Otherwise it is kept only for the current session.
6. Save the connection and update the calendar.

The application imports 30 days before and 90 days after the selected date. On the Analytics page, synchronization uses that page's anchor date. Automatic loading at startup is optional; periodic polling is not implemented.

Change imported titles, scheduled times and recurrence rules in Mail.ru. Categories, local execution status, actual time and comments are maintained here and survive synchronization. Repeated imports preserve event identity. The original plan is never overwritten by synchronization.

A missing event in a bounded server response is **not proof of deletion**: it remains available with a source warning. Network, authorization and parse failures preserve the previous data. A recoverable `calendar-data 404` can produce an explicitly marked partial import; disappearance detection is disabled for that import.

After importing a calendar, switching accounts/collections is blocked. The display time zone cannot be changed once schedule events exist. UTC/TZID values are converted on import; floating times use the selected zone.

Before relying on a connection, use a synthetic appointment to verify initial import, duplicate-free reimport, rescheduling after plan fixation, preservation of actual time/comments, and a recurring event with one moved occurrence.

## Daily workflow

1. Select the date and refresh Mail.ru.
2. Review the schedule, conflicts and free intervals within the 07:00–19:00 workday.
3. Fix the original plan once the day is agreed. Fixation is disabled during synchronization; missing, partial, failed or older-than-30-minute coverage produces a warning.
4. Record actual start/end times and execution status in the event card. Missing actual time is never replaced with scheduled time.
5. Use **Add event** or **Ctrl+N** for local planning or post-factum unplanned work.
6. Review analytics and incomplete actual-time records; use History to inspect changes.

A local event already included in the original plan cannot be deleted; cancel it while retaining its baseline. Imported events cannot be deleted locally. Post-factum local work is always unplanned. A baseline event moved to another day remains planned; ordinary events on an unfixed day have unknown work origin.

Plan fixation preserves the category, tracking flag and time tolerance used for baseline calculations. Later settings changes do not rewrite those saved rules. All-day events are displayed separately and do not contribute 24 hours of planned work.

## Analytics and exports

Reports cover a day, Monday–Sunday week or calendar month. Calendar search and display-layer filters do not filter the report. By default, reports include tracked categories; all categories can be included explicitly.

| Metric | Meaning |
| --- | --- |
| Plan completion | Completed baseline events / all baseline events starting in the period; period totals are not averages of daily percentages |
| Confirmed actual time | Actual intervals of completed or partially completed events, clipped to report/day boundaries |
| Unplanned share | Confirmed unplanned time / all confirmed actual time; unknown-origin time makes this a lower bound, shown with `≥` |
| Start/duration deviation | Actual minus original plan; summary cards use absolute deviations so early and late values do not cancel out |
| Completed without time | Completed events missing a full actual interval, excluding current all-day events |

No plan or actual data produces an undefined metric rather than a misleading zero. Deviation comparisons use complete original/actual intervals and the saved tolerance; equality with the tolerance is allowed. Overlapping actual intervals are summed, with duplicated minutes reported explicitly.

Reports show plan-fixation coverage, complete Mail.ru loading coverage, source warnings and missing actual time. Loading coverage is not a guarantee that the remote calendar is still current. Drill down by day, category or event; open an event to correct its actual time.

Period CSV exports include a total row and every day in the selected period. Files use UTF-8 with BOM, semicolons and decimal commas. Undefined values are blank. Reports are read from a consistent SQLite snapshot and do not modify the plan or fact records.

## History

All retained audit records are accessible, including entries beyond the former 300-record view. Pages contain 50, 100 or 200 entries.

- Search covers the entire journal, including readable descriptions and former event titles, not only the visible page.
- Search, event and change-date filters can be combined. Date endpoints are inclusive and refer to audit timestamps, not meeting dates.
- Selecting an event uses its ID, so identical titles do not mix unrelated histories. Deleted and archived event history remains readable.
- Double-click or press Enter for the complete change description. Existing events can be opened from their history entries.
- Older pages keep their position when new entries arrive. Refresh or return to the first page to see new records.

Browsing and searching do not delete or rewrite the original audit journal.

## Backups and recovery

### Routine backups and restoration

Use **Settings → Data and backups** to choose a backup directory, create a manual copy or restore a verified copy. Daily backup is enabled by default and retains 30 automatic copies. The application checks at startup and every 15 minutes while open; it creates at most one scheduled copy per day when the previous copy remains present. No backup runs while the application is closed.

Retention removes only this database's old automatic copies. Manual, migration, update and safety copies are not automatically rotated. Consider a protected location on another disk for protection against loss of the working disk.

Normal restoration validates the selected copy, creates a safety backup of the current database, prepares/migrates a separate staging database and replaces the live database only after validation. Restart the application after successful restoration.

Since **v0.12.1**, startup, normal restoration and emergency recovery use the same compatibility checks. A copy with a newer database schema or a newer recorded application version is rejected **before replacement**, even if its schema has not changed. The message identifies the recorded and installed application versions: update the application first or choose an older compatible copy. Invalid or empty version records are also rejected; legacy copies without a version record remain supported if their structure and data pass validation. Compatible older schemas are migrated only in staging.

The staged database is checked again before migration and after preparation, so the actual file being installed must pass the same gate as startup. A rejected copy does not replace working events, history or settings. Database schema version and application version are separate checks; neither is inferred from the backup filename.

### Emergency recovery at startup — v0.12.0

If the startup database check fails, the error dialog offers recovery without opening the main calendar:

1. Choose recovery and select a known-good `.db` or `.sqlite` backup.
2. Confirm replacement of the working events, history and settings.
3. The copy is checked, including its recorded application version, and prepared separately.
4. Original database and WAL/SHM/journal files, when present, are preserved under a unique directory inside `recovery` beside the working database. Damaged files are preserved as raw files rather than requiring a successful SQLite backup.
5. After successful replacement, reopen the application and verify the restored data.

The application retains its single-instance database lock during this process. Cancellation, invalid copies and preparation/archive failures do not replace the working database. The replacement failure path restores moved sidecar files. Keep preserved originals until the result has been checked. This feature restores a backup; it does not reconstruct records absent from that backup or repair a damaged file in place.

Other startup failures are reported through the normal startup error message and `startup-error.log` when the log can be written.

## Development and source-based launch

Normal users should use the standalone installer above. Source-based development uses Python **3.13 x64** and a separate virtual environment.

```powershell
git clone https://github.com/payuktv/director-calendar.git
cd director-calendar
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe main.py
```

For a source-based desktop shortcut, run `create_desktop_shortcut.pyw` with the configured environment or use the shortcut button in Settings. If the source directory moves, recreate the shortcut. Source-based and installed launches use the same default database location.

The stack is PySide6/Qt Widgets, SQLite, requests, icalendar, recurring-ical-events and Windows Vault through keyring. Package metadata accepts Python 3.13–3.14, but CI and distribution builds currently use Python 3.13.

## Tests and Windows packaging

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:DIRECTOR_CONTROL_DATA_DIR = Join-Path $env:TEMP 'director-calendar-tests'
.\.venv\Scripts\python.exe -m ruff check director_control tests scripts --select F
.\.venv\Scripts\python.exe -m pytest -q --junitxml=pytest-results.xml
.\.venv\Scripts\python.exe scripts\verify_test_results.py pytest-results.xml --platform Windows
```

The **Tests** workflow runs unit and GUI tests on Windows and Linux. Missing/empty JUnit reports, failures and skipped tests fail verification. Windows must include the native shortcut integration test. Linux excludes that Windows-only module during collection and uses `--platform Linux` for report verification.

Build on Windows x64 with Python 3.13 and Inno Setup 6:

```powershell
./scripts/build_windows.ps1
```

Build dependencies are pinned in `packaging/requirements-windows.lock`. PyInstaller uses `packaging/director-calendar.spec`; Inno Setup uses `packaging/installer.iss`. Outputs are written to `dist/artifacts`.

**Windows distribution** builds the current source and the highest published version below it for upgrade acceptance, including published pre-releases. Until the first release, it uses the pinned v0.10.0 bootstrap revision. It checks installation, GUI startup, update/reinstallation, downgrade/running-app protection, Unicode paths, backup behavior and preservation of data/credentials after uninstall. Bundled Qt, calendar parsing, time zones, TLS certificates and Vault are exercised. Artifacts are uploaded only after distribution acceptance passes.

**Release** reuses both the Tests and Windows distribution workflows at its own source commit and publishes their verified Windows artifact only when both succeed. Add English notes under `releases/vMAJOR.MINOR.PATCH.md` and merge into `main` to start a release, or run Release manually from Actions on `main`. Tags and published files are never overwritten by this process. See [release procedure and retry rules](docs/RELEASING.md).

Hosted runners still have Python installed, although the packaged child processes run without Python on PATH. These checks do not replace acceptance on a clean target Windows computer and the real Mail.ru account.

## Version conventions

- Use **`vMAJOR.MINOR.PATCH`** in documentation, Git tags and release titles, for example **v0.12.1**.
- Write version descriptions, release notes, commit messages and PR titles/descriptions in English.
- Keep machine-readable package versions and `__version__` numeric (`0.12.1`). Installer filenames currently follow that numeric form; do not rename them in instructions.
- Keep `pyproject.toml`, `director_control/__init__.py` and current-version documentation aligned when releasing an application change.
- Documentation-only changes do not require an application version bump. Do not label a build **v1.0.0** until release acceptance is complete.

### Recent milestones

| Version | Main change |
| --- | --- |
| v0.12.1 | Shared backup compatibility checks before normal/emergency restoration and on startup |
| v0.12.0 | Startup recovery from a verified backup with damaged originals preserved separately |
| v0.11.0 | Standalone Windows installer/portable package and verified update backups |
| v0.10.0 | Full-history pagination, search and readable change descriptions |
| v0.9.0 | Daily/weekly/monthly analytics and period CSV exports |
| v0.8.0 | Backup/restore controls, saved baseline rules, edit-conflict and single-instance protection |
| v0.7.0 | Local planned events and post-factum unplanned work |
| v0.6.0 | Desktop shortcut launch |
| v0.5.0 | Light and dark themes |

Earlier implementation details remain available in the repository's commit and pull-request history.

## Limits and release readiness

- One local user/database and one Mail.ru calendar; no multi-PC synchronization or calendar write-back.
- Manual plan fixation; no automatic daily fixation or background service when the app is closed.
- No periodic Mail.ru polling or automatic application update download.
- Secondly/minutely recurrences and timed events with zero/undefined duration are unsupported. Invalid input stops parsing without applying the import. Series changes can require manual review of old occurrences.
- The database stores local display-zone times without offsets; changing the zone after events exist is blocked.
- Authenticode signing is not configured yet. Clean Windows acceptance and real-account checks remain required before v1.0.0.

## Data privacy and further documentation

The SQLite database, audit history, CSV exports, backups and preserved recovery files can contain confidential schedule information. They are not encrypted by the application. Protect the Windows account, disk and backup location according to company policy. Passwords are not stored in SQLite; never commit databases, credentials or real calendar exports.

- [Windows distribution details](docs/WINDOWS-DISTRIBUTION.md) — additional operational/build notes, currently in Russian.
- [Release procedure](docs/RELEASING.md) — publication gates, previous-version selection and retries.
- [Original stack decision](docs/ADR-0001-stack.md) — historical rationale; the current packaging implementation uses PyInstaller.
- [Mail.ru integration decision](docs/ADR-0002-mail-calendar.md) — protocol rationale and historical implementation notes.

The application is named **Director Calendar**. The Python package name `director-control` and data directory `DirectorControl` remain unchanged for compatibility.
