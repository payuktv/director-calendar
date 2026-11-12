# v1.0.0 acceptance record

The frozen functional scope passed acceptance on **2026-11-12** against **v0.13.10**, commit `5f4135269b8cb9a98e6e84b9ba3ebdb997f74aa6`. v1.0.0 changes the version and release documentation without changing application behavior, the database schema or runtime dependencies.

The accepted scope is the single-user Windows application with read-only Mail.ru import, local events, plan/fact tracking, analytics, history and backup/recovery. The owner authorized promotion to stable v1.0.0 after reviewing the completed acceptance.

## Automated candidate checks

[Candidate Release run](https://github.com/payuktv/director-calendar/actions/runs/43210488144):

- Full Windows suite: **887 passed**, no failures or skips.
- Full Linux suite: **886 passed**, no failures or skips; the Windows-only module is excluded from Linux collection.
- Windows distribution acceptance passed, including installation, upgrade, reopening, data/credential preservation, backup/recovery, calendar write validation and the paired XML runtime.
- The candidate tag and eight verified release attachments were published from the tested commit.

The stable version must independently pass the same full platform and distribution gates at its own commit. Its [Release run](https://github.com/payuktv/director-calendar/actions/workflows/release.yml) and `distribution-check.json`, `upgrade-source.json` and `release-manifest.json` attachments provide the final version-specific evidence. Candidate results do not replace those checks.

## Target-system acceptance

Environment: the owner's existing **Windows 10 x64, build 19045**, ordinary Windows account and installed v0.13.10 executable. The owner performed installation. Standalone diagnostics used a fresh application data profile with development-runtime paths removed. This was neither a fresh Windows installation nor a new Windows user account.

| Check | Result and evidence |
| --- | --- |
| Installed runtime and independent launch | Passed. The installed executable's diagnostics verified GUI construction, calendar parsing, time zones, TLS certificates, Vault, backups/recovery and validation gates. Python 3.14.10, Expat 2.10.0 in both XML modules, SQLite 3.54.1 and OpenSSL 3.5.9 matched the release policy. |
| Existing-data update | Passed. The pre-update backup from v0.13.7 and the v0.13.10 database retained prior events, categories, history, original plan, actual time, comments, local statuses and settings. Additional status edits were reconciled with their pre-acceptance audit records. |
| Real Mail.ru synchronization | Passed. The installed application completed synchronization, closed normally, reopened and completed another synchronization. A separate worker retry also completed successfully. No Mail.ru events were created, edited or removed by acceptance. |
| Source-change scenarios | Passed using synthetic responses and an isolated database: withdraw an unfrozen missing event, retain a frozen plan, retain local cancellation after source removal, and preserve identity for a changed recurrence instance. The actual installed parsing worker and matching v0.13.10 storage code were used; the resulting database reopened successfully. |
| Cancellation and retry | Passed. Cancelling the installed worker preserved the prior database; the later real-account retry succeeded and its database reopened. |
| Backup restoration | Passed. A synthetic backup restored the expected data in an isolated profile and reopened successfully. Installed diagnostics also exercised normal/emergency restoration and rejection of malformed backups. |
| Working-data preservation during acceptance | Passed. Plan, facts, comments, local events, manual statuses, fixation records, categories, history and settings remained intact. |

The main window, displayed version and final synchronization state were observed through the accessibility tree and application records. Screenshot capture timed out, so this record does not claim a pixel-level visual review. The initial restricted diagnostic environment could not access Windows Vault; the same installed-executable check passed in the ordinary user context.

Detailed local evidence is retained in the workspace acceptance report and JSON records. Databases, credentials, account identifiers and real calendar contents are intentionally excluded from the repository.

## Release decision and remaining scope

The agreed functional acceptance is complete; no blocking failure remains in this checklist. Promote the same scope to v1.0.0 after its mandatory automated release gates pass. Installation of the stable build remains the owner's responsibility.

Authenticode signing, automatic update downloads, additional Windows/display coverage, advisory monitoring and new features remain later work. The installer is unsigned; the application does not encrypt its local database or backups. Mail.ru remains read-only. These documented limitations do not reopen the completed acceptance scope.
