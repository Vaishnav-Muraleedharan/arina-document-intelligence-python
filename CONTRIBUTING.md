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
                                                                          │
                                                                    publish.yml ──► PyPI (OIDC)
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

Merging the release PR tags `vX.Y.Z`, publishes a GitHub Release with the changelog
section, and triggers `publish.yml`, which builds once and uploads to PyPI with
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/) — no tokens stored.

**Bootstrapping the first release.** The manifest starts at `0.1.0`, matching
`pyproject.toml`, so there is nothing for release-please to bump yet. Publish `0.1.0` by
hand once: create tag `v0.1.0` and a GitHub Release from it. From then on release-please
takes over.

**Trying it before touching PyPI.** Actions → Publish → Run workflow → `testpypi`. Then
`pip install -i https://test.pypi.org/simple/ arina-document-intelligence`.

### One-time setup (per GitHub repo, per index)

1. On [TestPyPI](https://test.pypi.org) and [PyPI](https://pypi.org): Account → Publishing →
   *Add a new pending publisher*: project `arina-document-intelligence`, owner `<GitHub
   owner>`, repository `arina-document-intelligence-python`, workflow `publish.yml`,
   environment `testpypi` / `pypi`.
2. In GitHub: Settings → Environments → create `testpypi` and `pypi`. Add a required
   reviewer on `pypi` if you want a human approval before every publish.
3. Settings → Actions → General → Workflow permissions: *Read and write*, and allow
   GitHub Actions to create pull requests (release-please needs both).

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
