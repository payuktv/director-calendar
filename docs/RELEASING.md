# Releasing Director Calendar

## Prepare a version

1. Update the numeric version in `pyproject.toml` and `director_control/__init__.py` for an application change. Keep the README current. Distribution-process-only changes do not require an application version bump before its first published release.
2. Add `releases/vMAJOR.MINOR.PATCH.md`, headed by `# vMAJOR.MINOR.PATCH`, with English changes, installation/update instructions and known limitations. Use `v` for tags, release titles, commit and PR version references; package metadata and installer filenames remain numeric.
3. Merge the reviewed changes into `main` after normal PR checks pass. Changing a file under `releases/` on `main` starts **Release**. It can also be run manually from Actions using `main`.

## Publication gates

**Release** calls **Tests** with `suite: full` and **Windows distribution** at its own source commit. Both Windows and Linux tests must pass without skips; the Windows shortcut test remains mandatory. The distribution must pass installation, upgrade, launch, reinstallation, uninstall/data-preservation and backup/recovery checks. Focused PR success cannot replace these full release checks.

PR tests run on Windows with affected-area selection and a conservative full-suite fallback. Ordinary branch pushes do not duplicate them, and main pushes do not independently duplicate Release's tests or package build. Packaging/native lifecycle changes also run distribution acceptance on the PR. Other changes receive that check once at release. PR concurrency cancels superseded runs; release publication is never cancelled by that policy. See [testing policy](TESTING.md).

The publish job depends on both complete workflows. It downloads only the artifact from that same Release workflow run, checks its exact file set, version, source commit, binary checksums and all required acceptance flags, and matches the recorded upgrade source with the acceptance report. No files are rebuilt for publication.

Only the publish job has `contents: write`. It creates the exact `vMAJOR.MINOR.PATCH` tag on the tested commit, uploads the full set into a **draft**, verifies the uploaded sizes and SHA-256 digests, then publishes. A changed `main` or tag aborts publication. Releases below v1.0.0 are marked **Pre-release**; the workflow does not declare production readiness or advance versions itself.

The uploaded set contains the installer, portable ZIP, checksums for all attachments, dependency/build information, distribution acceptance report, previous-version record and release manifest. GitHub adds its source-code archives separately. The download channel is the repository's **Releases** page; Actions artifacts are temporary CI outputs, not the permanent installation source.

## Upgrade baseline

The Windows workflow selects the highest published version strictly below the candidate, including published pre-releases but excluding drafts and non-version tags. It resolves the source tag to a fixed commit and checks out that source to seed the old database. For upgrade acceptance it downloads the actual published installer instead of rebuilding the old application. The API asset digest/size and the verified release manifest must agree with the selected version and commit; the tag is checked again after download. The installer is rehashed immediately before execution. Its digest, asset ID and release ID are recorded in `upgrade-source.json`; publication also verifies that acceptance used this digest. A download/metadata/checksum failure stops the workflow, without silently substituting a rebuilt binary. GitHub authorization is removed on cross-host asset redirects.

Before the first release only, the bootstrap baseline is v0.10.0 at `a7e524281a3026d501eb7232d68008f09700e3c3`; that baseline is built with the current packaging toolchain because no published installer exists. A network/API failure does not silently select that baseline. Once v0.12.1 is published, a later version uses it (or a newer intervening published version) automatically.

## Retry and preservation

- A failed test or packaging job prevents the publish job from running. Resolve the failure and rerun the workflow.
- An upload/verification failure leaves an unpublished draft. Rerun **Release** from the same commit; it may replace only that draft's assets. Each retry downloads a fresh CI artifact.
- A published release is never replaced by this workflow. Rerunning its exact commit is a no-op; reusing its version on another commit fails. For application changes, choose a new version.
- Do not manually move release tags. If `main` advanced before publication, run Release from the current main revision. If the old attempt already created a tag/draft, investigate it and use a new version rather than moving a tag automatically.
- Release jobs are serialized without cancelling an in-progress publication.

Before v1.0.0, complete real Windows/Mail.ru acceptance and the agreed operational checks. Authenticode signing and automatic update downloads are separate work.

## Native security and installed contents

Publication requires `sqlite_patched`, `untrusted_backup_rejected`, `obsolete_files_removed`, `user_files_preserved`, `installed_file_manifest` and `reparse_path_rejected`, plus the pinned SQLite runtime version and source ID. The packaged executable exercises both restore paths against foreign schemas. Installer acceptance compares all installed file hashes, simulates historical retired files, retains unrelated user files, and rejects a junction without changing its external target. Update the explicit retired-file list when packaging removes files. Upstream SQLite archive hashes are pinned in `scripts/prepare_sqlite.py`; an unexpected archive or runtime fails the build.

`backup_settings_validated` and `backup_destination_local` are also mandatory: the installed executable rejects malformed settings before restoration/startup, preserves normal restoration's local backup policy, resets emergency recovery to local defaults, and checks that newly added synthetic data is backed up only to the intended destination. Imported backup paths and last-copy records must not choose the automatic backup destination.

The build uses standard CPython 3.14.10 x64 from `.python-version` and hash-verified pip 26.3 from `packaging/build-tools.lock`. Changing Python or either build lock recreates the isolated build venv. `runtime_patched` and exact Python/Expat/OpenSSL values from the packaged executable are mandatory publication checks; `director_control/runtime_versions.py` defines the accepted runtime. The separate SQLite override is still required. Keep the runtime policy and interpreter pin in sync, and retire exact old ABI filenames on interpreter upgrades.
