# Releasing Director Calendar

## Prepare a version

1. Update the numeric version in `pyproject.toml` and `director_control/__init__.py` for an application change. Keep the README current. Distribution-process-only changes do not require an application version bump before its first published release.
2. Add `releases/vMAJOR.MINOR.PATCH.md`, headed by `# vMAJOR.MINOR.PATCH`, with English changes, installation/update instructions and known limitations. Use `v` for tags, release titles, commit and PR version references; package metadata and installer filenames remain numeric.
3. Merge the reviewed changes into `main` after normal PR checks pass. Changing a file under `releases/` on `main` starts **Release**. It can also be run manually from Actions using `main`.

## Publication gates

**Release** calls the existing **Tests** and **Windows distribution** workflows at its own source commit. Both Windows and Linux tests must pass without skips; the Windows shortcut test remains mandatory. The distribution must pass installation, upgrade, launch, reinstallation, uninstall/data-preservation and backup/recovery checks.

The publish job depends on both complete workflows. It downloads only the artifact from that same Release workflow run, checks its exact file set, version, source commit, binary checksums and all required acceptance flags, and matches the recorded upgrade source with the acceptance report. No files are rebuilt for publication.

Only the publish job has `contents: write`. It creates the exact `vMAJOR.MINOR.PATCH` tag on the tested commit, uploads the full set into a **draft**, verifies the uploaded sizes and SHA-256 digests, then publishes. A changed `main` or tag aborts publication. Releases below v1.0.0 are marked **Pre-release**; the workflow does not declare production readiness or advance versions itself.

The uploaded set contains the installer, portable ZIP, checksums for all attachments, dependency/build information, distribution acceptance report, previous-version record and release manifest. GitHub adds its source-code archives separately. The download channel is the repository's **Releases** page; Actions artifacts are temporary CI outputs, not the permanent installation source.

## Upgrade baseline

The Windows workflow selects the highest published version strictly below the candidate, including published pre-releases but excluding drafts and non-version tags. It resolves the source tag to a fixed commit and records both the selected version and the commit in the output. The previous source is built with the current packaging toolchain and used for real installation/upgrade testing.

Before the first release only, the bootstrap baseline is v0.10.0 at `a7e524281a3026d501eb7232d68008f09700e3c3`. A network/API failure does not silently select that baseline. Once v0.12.1 is published, a later version uses it (or a newer intervening published version) automatically.

## Retry and preservation

- A failed test or packaging job prevents the publish job from running. Resolve the failure and rerun the workflow.
- An upload/verification failure leaves an unpublished draft. Rerun **Release** from the same commit; it may replace only that draft's assets. Each retry downloads a fresh CI artifact.
- A published release is never replaced by this workflow. Rerunning its exact commit is a no-op; reusing its version on another commit fails. For application changes, choose a new version.
- Do not manually move release tags. If `main` advanced before publication, run Release from the current main revision. If the old attempt already created a tag/draft, investigate it and use a new version rather than moving a tag automatically.
- Release jobs are serialized without cancelling an in-progress publication.

Before v1.0.0, complete real Windows/Mail.ru acceptance and the agreed operational checks. Authenticode signing and automatic update downloads are separate work.
