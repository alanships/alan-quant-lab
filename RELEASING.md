# Releasing

This runbook publishes `okx-perp-reliable` to PyPI from GitHub Actions using
PyPI Trusted Publisher. Do not create or store a PyPI API token for this
project.

## Release history

| Version | Tagged | Notes |
|---|---|---|
| `v0.1.0a1` | 2026-05-09 | First public alpha. Reconciliation contract pinned; OKX USDT-perp swap REST place + cancel + query only. Yanked after public-history cleanup. PyPI: <https://pypi.org/project/okx-perp-reliable/0.1.0a1/> |
| `v0.1.0a2` | 2026-05-09 | Current public alpha after public-history cleanup. PyPI: <https://pypi.org/project/okx-perp-reliable/0.1.0a2/> |

`v0.1.0a1` was yanked because a history rewrite changed the source backing
that version number. Per PyPI policy, version numbers are not re-used, so the
rewritten source was published as `0.1.0a2`.

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
git commit -m "Release <NEW_VERSION>"

# 4. Run the pre-push check below.

# 5. Tag and push:
git tag v<NEW_VERSION>
git push origin main --tags

# 6. Watch the workflow:
# https://github.com/alanships/alan-quant-lab/actions/workflows/publish.yml

# 7. Verify PyPI:
# https://pypi.org/project/okx-perp-reliable/<NEW_VERSION>/
```

Use either a tag push or a GitHub Release published event for a given version.
If both fire for the same version, the second publish can fail because PyPI
does not allow overwriting existing files.

## Pre-push check

Before pushing the release commit and tag, run the privacy/style checks
defined in `.codex/PUBLIC_COMMIT_STYLE.md`:

```bash
# Last 10 messages — read as a stranger.
git log --oneline -10

# Anything from .codex/ being pushed?
git diff --stat origin/main..HEAD | grep -E '^\s*\.codex/' \
  && echo "REVIEW: .codex/ in push" || echo "no .codex/ leaks"

# Internal tooling words in pending messages?
git log --format=%B origin/main..HEAD | \
  grep -iE 'codex|claude|gpt|llm|\bagent\b|task [0-9]+|card [0-9]+' \
  && echo "REVIEW: internal refs found" || echo "messages clean"
```

If any check surfaces something, fix before pushing. Once a public tag is
pushed, do not force-push; record the lesson and tighten the rules instead.

## Post-release smoke test

After the publish workflow goes green and PyPI shows the new version, verify
in a fresh virtualenv that the package is actually installable and importable:

```bash
python -m venv /tmp/okx-perp-reliable-smoke
source /tmp/okx-perp-reliable-smoke/bin/activate
pip install --no-cache-dir okx-perp-reliable==<NEW_VERSION>
python -c "
from okx_perp_reliable import (
    ReliablePerpClient,
    OrderSide,
    OrderType,
    ResultStatus,
    AuthenticationError,
    RateLimitError,
)
print('imports OK', ReliablePerpClient.__module__)
"
deactivate
rm -rf /tmp/okx-perp-reliable-smoke
```

If any import fails, the release is broken even though the workflow went green.
Yank the version on PyPI, fix the bug, bump to the next version, and
re-release. Never re-use a broken version number.

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
