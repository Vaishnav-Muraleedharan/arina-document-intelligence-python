#!/usr/bin/env python3
"""Import a Scalar-generated SDK zip into this repository.

    python scripts/import_sdk.py path/to/arina-document-intelligence-api-python.zip

This is the manual counterpart of Scalar's paid "scalar-next" merge. It keeps the
repository split into three kinds of paths:

* **Generated** - replaced wholesale from the zip every import. Never edit these by
  hand; the next import overwrites them.
* **Ours** - never touched by the import: ``src/arina_document_intelligence/lib/``,
  ``tests/`` (except Scalar's ``tests/smoke-test.py``), ``scripts/``, ``.github/``,
  release tooling and ``CONTRIBUTING.md``.
* **Preserved** - generated once, then owned by us: ``pyproject.toml``, ``README.md``
  and ``LICENSE``. They are copied only when missing. If the zip's version differs from
  ours, a diff is printed so the change can be ported deliberately (for example a new
  runtime dependency in ``pyproject.toml``).

After copying, the package version is restored from ``pyproject.toml`` into the
generated ``_version.py``, because the zip always says ``0.1.0`` while release-please
owns the real version.

Exit status is non-zero on a malformed zip. It is zero even when diffs are printed:
review them, port what matters, commit.
"""

from __future__ import annotations

import difflib
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "src" / "arina_document_intelligence"

# Paths (relative to the repo) that the zip owns. Directories are replaced entirely,
# except for the OURS_INSIDE_GENERATED entries nested inside them.
GENERATED = [
    "src/arina_document_intelligence",
    "api.md",
    "SKILL.md",
    ".claude",
    "scalar-sdk.manifest.json",
    "SECURITY.md",
    "tests/smoke-test.py",
    ".gitignore",
]

# Ours, even though they live under a generated directory.
OURS_INSIDE_GENERATED = [
    "src/arina_document_intelligence/lib",
]

# Generated once, then edited by us. Copied only when absent; otherwise diffed.
PRESERVED = [
    "pyproject.toml",
    "README.md",
    "LICENSE",
]

VERSION_RE = re.compile(r'^(version\s*=\s*)"([^"]+)"', re.MULTILINE)
VERSION_PY_RE = re.compile(r'^(__version__\s*=\s*)"([^"]+)"', re.MULTILINE)


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def extract(zip_path: Path, into: Path) -> Path:
    """Unzip and return the directory that holds pyproject.toml."""
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(into)
    candidates = [p.parent for p in into.rglob("pyproject.toml")]
    if len(candidates) != 1:
        fail(f"expected exactly one pyproject.toml in the zip, found {len(candidates)}")
    root = candidates[0]
    if not (root / "src" / "arina_document_intelligence" / "_client.py").exists():
        fail("zip does not contain src/arina_document_intelligence/_client.py")
    return root


def replace_generated(source: Path) -> list[str]:
    """Copy generated paths from ``source`` into the repo. Returns what was replaced."""
    replaced: list[str] = []
    keep = [REPO / p for p in OURS_INSIDE_GENERATED]

    for rel in GENERATED:
        src, dst = source / rel, REPO / rel
        if not src.exists():
            print(f"note: zip has no {rel}; leaving ours in place")
            continue
        if src.is_dir():
            if dst.exists():
                for child in dst.iterdir():
                    if any(child == k or k.is_relative_to(child) for k in keep):
                        # Contains (or is) one of ours: descend instead of deleting.
                        _remove_generated_within(child, keep)
                    else:
                        shutil.rmtree(child) if child.is_dir() else child.unlink()
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        replaced.append(rel)
    return replaced


def _remove_generated_within(directory: Path, keep: list[Path]) -> None:
    """Delete everything under ``directory`` except the ``keep`` paths."""
    if directory in keep:
        return
    if directory.is_file():
        directory.unlink()
        return
    for child in directory.iterdir():
        if any(child == k or k.is_relative_to(child) for k in keep):
            _remove_generated_within(child, keep)
        else:
            shutil.rmtree(child) if child.is_dir() else child.unlink()


def handle_preserved(source: Path) -> tuple[list[str], list[str]]:
    """Bootstrap missing preserved files; diff the rest. Returns (created, differing)."""
    created: list[str] = []
    differing: list[str] = []
    for rel in PRESERVED:
        src, dst = source / rel, REPO / rel
        if not src.exists():
            continue
        if not dst.exists():
            shutil.copy2(src, dst)
            created.append(rel)
            continue
        theirs = src.read_text(encoding="utf-8").splitlines(keepends=True)
        ours = dst.read_text(encoding="utf-8").splitlines(keepends=True)
        if theirs != ours:
            differing.append(rel)
            print(f"\n--- {rel}: generated version differs from ours (ours is kept) ---")
            sys.stdout.writelines(difflib.unified_diff(ours, theirs, fromfile=f"ours/{rel}", tofile=f"zip/{rel}", n=1))
    return created, differing


def restore_version() -> str:
    """Write the version from pyproject.toml into the generated _version.py."""
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    match = VERSION_RE.search(pyproject)
    if not match:
        fail("could not find a version line in pyproject.toml")
    version = match.group(2)
    version_py = PACKAGE / "_version.py"
    text = version_py.read_text(encoding="utf-8")
    new_text, count = VERSION_PY_RE.subn(rf'\g<1>"{version}"', text)
    if count != 1:
        fail("could not find __version__ in the generated _version.py")
    version_py.write_text(new_text, encoding="utf-8")
    return version


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    zip_path = Path(argv[1]).expanduser().resolve()
    if not zip_path.is_file():
        fail(f"no such file: {zip_path}")

    with tempfile.TemporaryDirectory() as tmp:
        source = extract(zip_path, Path(tmp))
        replaced = replace_generated(source)
        created, differing = handle_preserved(source)

    version = restore_version()

    print("\nimport complete")
    print(f"  replaced (generated): {', '.join(replaced)}")
    if created:
        print(f"  created (preserved, first import): {', '.join(created)}")
    if differing:
        print(f"  review (preserved, zip differs): {', '.join(differing)}")
    print(f"  version restored to {version} in _version.py")
    print("\nnext: git status, run the tests, then commit as 'chore(sdk): import generated <date>'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
