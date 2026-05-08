# Releasing

This runbook publishes `okx-perp-reliable` to PyPI from GitHub Actions using
PyPI Trusted Publisher. Do not create or store a PyPI API token for this
project.

## One-time setup

Alan does this once, manually.

1. Reserve the PyPI project name with a pending publisher:
   - Go to <https://pypi.org/manage/account/publishing/>.
   - Click "Add a new pending publisher".
   - Fill:
     - PyPI Project Name: `okx-perp-reliable`
     - Owner: `alanships`
     - Repository name: `alan-quant-lab`
     - Workflow name: `publish.yml`
     - Environment name: leave blank for the first release.
   - This reserves the project name and lets the first OIDC publish work
     without an initial token upload.

2. Optional: create a `pypi` GitHub environment with required reviewers if you
   want a manual approval gate before each publish. The current workflow does
   not require this environment.

3. Optional: test with TestPyPI first. TestPyPI also supports trusted
   publishers. Configure a parallel pending publisher there and add a separate
   workflow in a future card if needed.

## Cutting a release

Run these steps locally:

```bash
# 1. Confirm everything on main is green:
poetry run pytest tests -v
poetry run ruff check .
poetry run black --check .

# 2. Bump version in pyproject.toml, for example 0.1.0a1 -> 0.1.0a2.
# Edit by hand; pyproject.toml is the single source of truth.

# 3. Commit the version bump:
git add pyproject.toml
git commit -m "release: v<NEW_VERSION>"

# 4. Tag and push:
git tag v<NEW_VERSION>
git push origin main --tags

# 5. Watch the workflow:
# https://github.com/alanships/alan-quant-lab/actions/workflows/publish.yml

# 6. Verify PyPI:
# https://pypi.org/project/okx-perp-reliable/<NEW_VERSION>/
```

Use either a tag push or a GitHub Release published event for a given version.
If both fire for the same version, the second publish can fail because PyPI
does not allow overwriting existing files.

## Manual trigger

If a publish run failed before upload completed, go to GitHub Actions, open the
`publish` workflow, choose "Run workflow", and select the branch. Use this
rarely. If the version was already uploaded to PyPI, bump the version instead.

## If a release fails

- Trusted publisher misconfigured: fix the PyPI pending-publisher form, then
  re-run the workflow.
- Version already exists on PyPI: never reuse the version number. Bump the
  version in `pyproject.toml`, commit, tag, and publish again.
- Build metadata looks wrong: run `poetry build` locally and inspect `dist/`
  plus the generated package metadata before tagging again.

## Yanking a bad release

Use PyPI yanking instead of deletion:
<https://pypi.org/project/okx-perp-reliable/#history> -> choose the version ->
"Options" -> "Yank".

Never delete a published version. PyPI still prevents reusing that version
number after deletion, and yanking is reversible.
