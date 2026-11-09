# Releasing

How to cut a release of `aa_auto_sdr` and publish it to PyPI.

A pushed `vX.Y.Z` tag starts
[`.github/workflows/release.yml`](.github/workflows/release.yml). The workflow
uploads to PyPI over OIDC [trusted publishing](https://docs.pypi.org/trusted-publishers/),
so no API token is stored anywhere. The PyPI project `aa-auto-sdr` trusts this
repository, the `release.yml` workflow, and the `pypi` GitHub environment. Keep
both names exactly as they are, or PyPI rejects the upload.

## What the workflow does

The workflow has three jobs.

1. `build` runs for a tag push and for a manual run. It does the following:
   - Runs `ruff check`, `ruff format --check`, `uv lock --check`, and
     `scripts/check_version_sync.py`.
   - Runs the full test suite on Python 3.14.
   - For a tag push, checks that the tag is `v` plus the version in
     `src/aa_auto_sdr/core/version.py`.
   - Takes the release notes from the version's section in `CHANGELOG.md`. The
     job fails if that section is missing or empty.
   - Builds the wheel and the source package with `uv build`.
   - Checks that the packaged README has no relative links, with
     `scripts/check_distribution_readme_links.py`.
   - Installs the wheel into a new environment on every supported Python, and
     runs `--help`, `--exit-codes`, and `-V`. The `-V` output must show the
     version.
   - Writes `SHA256SUMS` and stores the packages, the sums, and the release
     notes as the `dist` artifact.
2. `publish` runs only for a tag push. It runs in the `pypi` environment, which
   waits for a reviewer to approve it. It checks the sums and uploads the
   packages to PyPI.
3. `github-release` runs after `publish`. It checks the sums and creates the
   GitHub Release. The release body is the `CHANGELOG.md` section, and the
   wheel, the source package, and `SHA256SUMS` are attached.

The `pypi` environment allows deployments only from tags that match `v*.*.*`.
A ruleset named "Protect release tags" stops anyone from deleting or moving a
`v*` tag.

## Steps

1. **Open a PR with the version bump and the changelog.**
   - In `src/aa_auto_sdr/core/version.py`, set `__version__` to the new `X.Y.Z`.
     This file is the single source of the version.
   - In `tests/test_version.py`, set the expected version to `X.Y.Z`.
   - Add a `## [X.Y.Z] — YYYY-MM-DD` section at the top of `CHANGELOG.md`.
   - `scripts/check_version_sync.py` runs in CI. It fails unless `version.py`,
     the `pyproject.toml` version setting, and the top `CHANGELOG.md` heading
     agree.

2. **Merge the PR.** `main` is protected, so the PR must pass the required
   checks first. Then merge it:
   ```bash
   gh pr merge <PR> --merge
   ```

3. **Optional dry run.** In the Actions tab, open the `release` workflow and
   click "Run workflow" on `main`. Only the `build` job runs, and nothing is
   uploaded. You can also run it from the terminal:
   ```bash
   gh workflow run release.yml --ref main
   ```

4. **Tag the merge commit and push the tag.**
   ```bash
   git checkout main && git pull
   git tag vX.Y.Z && git push origin vX.Y.Z
   ```
   The tag must be exactly `v` plus the version in `version.py`.

5. **Approve the `pypi` deployment.** When `build` passes, the `publish` job
   waits. Open the workflow run and click "Review deployments". To find the
   run from the terminal:
   ```bash
   gh run list --workflow release.yml --limit 1
   gh run view <RUN_ID> --web
   ```

6. **Check PyPI and the GitHub Release.**
   ```bash
   curl -s https://pypi.org/pypi/aa-auto-sdr/json \
     | python3 -c "import json,sys; print(json.load(sys.stdin)['info']['version'])"
   gh release view vX.Y.Z
   ```
   You can also open https://pypi.org/project/aa-auto-sdr/.

## Notes

- **No token.** Publishing uses OIDC trusted publishing. Never add a PyPI token
  to the repository or to the Actions secrets.
- **Do not create the GitHub Release by hand.** The `github-release` job creates
  it after the PyPI upload. A release that already exists for the tag makes the
  job update that release instead.
- **A run that fails before the upload has published nothing.** If the cause
  is outside the code, e.g., a network error, re-run the failed jobs from the
  Actions tab. If the code must change, fix it on `main` with a new PR, bump to
  the next patch version, and push a new tag. The tag ruleset blocks moving an
  existing tag.
- **PyPI versions cannot change.** You can never reuse a version number, even
  after a yank. If a publish is wrong, bump to the next patch and release again.
- **Docs-only and CI-only changes do not need a release.** Changes to
  documentation, workflows, and other files outside the package merge to `main`
  without a version bump or a PyPI upload. Bump the version only when the
  installed package changes.
