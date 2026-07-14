# Releasing

How to cut a release of `aa_auto_sdr` and publish it to PyPI.

Publishing is automated. A published GitHub Release triggers
[`.github/workflows/release.yml`](.github/workflows/release.yml), which builds the
sdist and wheel and uploads them to PyPI over OIDC
[trusted publishing](https://docs.pypi.org/trusted-publishers/) — no API token is
stored anywhere. The PyPI project `aa-auto-sdr` is registered to trust exactly this
repository, the `release.yml` workflow, and the `pypi` GitHub Environment.

## Steps

1. **Bump the version and changelog** on a branch:
   - Edit `src/aa_auto_sdr/core/version.py` — set `__version__` to the new `X.Y.Z`.
     This is the single source of truth for the version.
   - Add a `## [X.Y.Z] — YYYY-MM-DD` section to the top of `CHANGELOG.md` describing
     the change.
   - `scripts/check_version_sync.py` (run in CI) fails the build unless
     `version.py`, the `pyproject.toml` dynamic-version wiring, and the top
     `CHANGELOG.md` heading all agree.

2. **Merge to `main`.** Open a PR and let the required checks pass (`lint`, `test`,
   `check`, `gate`), then merge. `main` is protected, so this goes through a PR like
   any other change.

3. **Tag and publish the Release:**
   ```bash
   git checkout main && git pull
   git tag vX.Y.Z            # tag MUST be exactly v + the version in version.py
   git push origin vX.Y.Z
   gh release create vX.Y.Z --title "vX.Y.Z" --generate-notes
   ```
   Publishing the Release fires `release.yml`. Its first step re-checks that the tag
   equals `v<version.py>` and fails the run before uploading if they disagree.

4. **Verify it's live:**
   ```bash
   curl -s https://pypi.org/pypi/aa-auto-sdr/json \
     | python3 -c "import json,sys; print(json.load(sys.stdin)['info']['version'])"
   # or open https://pypi.org/project/aa-auto-sdr/
   ```

## Notes

- **No token.** Publishing uses OIDC trusted publishing. Never add a PyPI token to
  the repository or to Actions secrets for this.
- **The tag is load-bearing.** `release.yml` refuses to publish if `vX.Y.Z` does not
  match `version.py`. Tag the commit that carries the bumped version — that is, after
  step 2 merges.
- **PyPI versions are immutable.** A version number can never be reused, even after a
  yank. If a publish is wrong, bump to the next patch and release again.
- **Docs-only and CI-only changes do not need a release.** Documentation, workflow,
  and other non-package changes merge to `main` without a version bump or a PyPI
  publish. Only bump the version when the installed package changes.
