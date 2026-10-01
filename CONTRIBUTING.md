# Maintaining this SDK

This repository holds the Python SDK for the Arina Document Intelligence API. Most of the
client is **generated** from the API's public OpenAPI document; the rest — helpers,
tests, release automation — is written here. This page explains how the two coexist and
how a change travels from the API to a published package.

## The pipeline in one picture

```
API repo (Azure DevOps)              this repo (GitHub)                          registries
─────────────────────────            ─────────────────────────────────────       ──────────
src/*_models.py, routes              scripts/import_sdk.py <zip>   (manual)
   │  python openapi/spec.py build      │
   ▼                                    ▼
openapi.public.json  ──► Scalar ──► generated code replaced ──► PR ──► CI ──► main
(the contract)        (generator)        + lib/, tests/ kept                    │
                                                                    release-please PR
                                                                          │ merge
                                                                    tag vX.Y.Z + GitHub Release
                                                                          │ same run
                                                                    release.yml build ──► (Test)PyPI (OIDC)
```

Two independent cadences: the **API deploys** whenever the bot repo's pipeline runs; the
**SDK releases** when the contract or the helpers change. Additive API changes (new
optional field, new endpoint) need nothing special. A breaking change gets a new
`X-Api-Version` date in the spec and a major SDK bump.

## Three kinds of files

| Kind | Paths | Rule |
| --- | --- | --- |
| **Generated** | `src/arina_document_intelligence/**` (except `lib/`), `api.md`, `SKILL.md`, `.claude/`, `scalar-sdk.manifest.json`, `SECURITY.md`, `tests/smoke-test.py`, `.gitignore` | Never edit. Replaced wholesale by `scripts/import_sdk.py`. Fix problems upstream: in the OpenAPI document or the generator config. |
| **Ours** | `src/arina_document_intelligence/lib/`, `tests/` (except `smoke-test.py`), `scripts/`, `.github/`, `release-please-config.json`, `.release-please-manifest.json`, `CHANGELOG.md`, `CONTRIBUTING.md` | Normal code. Reviewed and tested like anything else. |
| **Preserved** | `pyproject.toml`, `README.md`, `LICENSE` | Generated once, then ours. The import script never overwrites them; it prints a diff when the generated version changed so you can port what matters (typically a new runtime dependency). |

Why this split works without a vendor's merge tool: generated and hand-written code
never share a file, so git has nothing to merge. Add helpers as new modules under
`lib/`, never inside a generated file.

## Regenerating after an API change

1. In the API repo: change the model or route, run `python openapi/spec.py build`, commit
   the regenerated `openapi/openapi.public.json` alongside.
2. Upload that document to the generator and download the Python zip.
3. Here, on a branch:
   ```sh
   python scripts/import_sdk.py ~/Downloads/arina-document-intelligence-api-python.zip
   git status                     # generated paths changed; lib/, tests/ untouched
   pytest                         # the wire-contract tests are the safety net
   git commit -am "feat(sdk): regenerate for <what changed in the API>"
   ```
   Use `feat:` when the API gained something, `fix:` when only behaviour/docs changed —
   the prefix decides the next version number.
4. Open a PR. CI runs lint, tests on the oldest and newest supported Python, builds the
   package and checks its metadata.
5. Merge. release-please opens or updates the release PR.

The import script restores the current version into the generated `_version.py`
(the zip always says `0.1.0`) and refuses zips that are not this SDK.

## Releasing

Releases are cut by [release-please](https://github.com/googleapis/release-please) from
Conventional Commits on `main`:

| Commit prefix | Effect while 0.x | Effect at 1.x+ |
| --- | --- | --- |
| `fix:` | patch (`0.1.0 → 0.1.1`) | patch |
| `feat:` | minor (`0.1.0 → 0.2.0`) | minor |
| `feat!:` or `BREAKING CHANGE:` footer | minor | major |
| `chore:`, `docs:`, `ci:`, `test:` | no release | no release |

Everything lives in one workflow, `.github/workflows/release.yml`. Merging the release PR
makes its next run tag `vX.Y.Z`, publish a GitHub Release with the changelog section, and
— in the same run — build that tag once and upload it with
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/). No tokens stored, no
manual step. End to end:

```
PR "fix: …" merged ─► release.yml: release-please opens "chore(main): release 0.1.1"
                            │ you merge it
                            ▼
                      release.yml: release-please tags v0.1.1 + GitHub Release
                            │ same run, `release_created == true`
                            ▼
                      build ─► publish-testpypi  or  publish-pypi
```

Why one file, and not a separate publish workflow: two platform rules force it.

- GitHub never starts a workflow for an event created with a workflow's own
  `GITHUB_TOKEN` — and that is the token release-please uses to create the GitHub
  Release. So `on: release` in another file would never fire.
- PyPI identifies a Trusted Publisher by workflow filename and
  [refuses reusable (called) workflows](https://docs.pypi.org/trusted-publishers/troubleshooting/#reusable-workflows-on-github).
  So the publish steps cannot live in a workflow that release.yml calls.

**Which index.** Automatic publishes are fail-safe: they go to **TestPyPI unless the
repository variable `RELEASE_INDEX` is exactly `pypi`** (Settings → Secrets and variables
→ Actions → Variables). A missing or mistyped variable can never reach the real index —
which matters, because a real upload is irreversible (the version is burned and, from a
personal account, the project name is claimed). Set `RELEASE_INDEX=pypi` once, from the
organisation's repository, to go live. The run summary states the version, tag and index
before anything is uploaded.

**Manual publish** (Actions → Release → Run workflow): pick the index and, optionally, a
tag as `ref`. Use it to bootstrap the first version, or to upload a version that was
tagged but failed to publish. Without `ref` it builds the default branch and skips the
tag check.

**Bootstrapping the first release.** The manifest starts at `0.1.0`, matching
`pyproject.toml`, so there is nothing for release-please to bump yet. Publish `0.1.0` by
hand once with the manual run, then tag it: `git tag v0.1.0 && git push origin v0.1.0`.
From then on release-please takes over.

Install from TestPyPI with
`pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple arina-document-intelligence`.
An index never accepts the same version twice, so each rehearsal needs a new version —
which is exactly what a `fix:` merge produces.

### One-time setup (per GitHub repo, per index)

1. On [TestPyPI](https://test.pypi.org) and [PyPI](https://pypi.org), add a GitHub
   publisher — under *Account → Publishing → Add a new pending publisher* before the
   project exists, or *Project → Manage → Publishing* once it does: project
   `arina-document-intelligence`, owner `<GitHub owner>`, repository
   `arina-document-intelligence-python`, **workflow `release.yml`**, environment
   `testpypi` on TestPyPI / `pypi` on PyPI. The workflow filename must be the file that
   contains the publish step; a stale entry for another filename yields
   `invalid-publisher`.
2. In GitHub: Settings → Environments → create `testpypi` and `pypi`. Add a required
   reviewer on `pypi` if you want a human approval before every publish.
3. Settings → Actions → General → Workflow permissions: *Read and write*, and allow
   GitHub Actions to create pull requests (release-please needs both).
4. Optional while rehearsing: no variable needed — TestPyPI is the default. When going
   live: repository variable `RELEASE_INDEX` = `pypi`.

## Local development

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
ruff check && ruff format --check
pytest
python -m build && twine check --strict dist/*
```

Tests never touch the network: `tests/conftest.py` binds the client to an
`httpx.MockTransport` that records requests, and the tests assert on the exact bytes —
for instance that `config` is one multipart form field holding JSON, which is what the
API's FastAPI routes read. `tests/smoke-test.py` is the generator's live smoke test;
run it by hand against a real deployment when you want an end-to-end check.

## Known follow-ups

- Regenerate once the generator config sets `readEnv: ARINA_GRID_API_KEY` and
  `defaultEnvPrefix: ARINA_GRID`; the current build reads `API_KEY_AUTH` and
  `ARINA_BASE_URL`, and its default base URL is a development sandbox.
- Replace `OWNER` in `pyproject.toml` `[project.urls]` with the GitHub owner.
- The `LICENSE` copyright holder should be the legal entity name.

