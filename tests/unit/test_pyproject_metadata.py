"""OSS.3: pin the publishable pyproject.toml metadata so a sloppy edit
cannot silently break the PyPI listing or the public contract.

Three cells:

  1. ``test_distribution_name_is_decoy_cli`` -- Q-OSS-1 RESOLVED 2026-06-01
     locks the dist name to `decoy-cli` (the import package + console
     script stay `decoy`).
  2. ``test_classifiers_cover_python_3_10_3_11_3_12`` -- the release-smoke
     gate runs against exactly those three versions; the classifiers must
     advertise the same matrix.
  3. ``test_project_urls_present`` -- the PyPI sidebar surfaces these;
     a missing URL is a quiet drop in the listing's discoverability.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

PYPROJECT = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"


def _load() -> dict:
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


def test_distribution_name_is_decoy_cli() -> None:
    """Q-OSS-1 RESOLVED 2026-06-01: PyPI dist is `decoy-cli`. A rename
    requires a deliberate edit to both pyproject.toml AND this test."""
    data = _load()
    assert data["project"]["name"] == "decoy-cli", (
        "PyPI distribution name drifted from `decoy-cli` (Q-OSS-1). "
        "Update pyproject.toml AND this test together if the rename is "
        "intentional."
    )


def test_console_script_name_is_decoy() -> None:
    """The console script stays `decoy` regardless of the dist rename."""
    data = _load()
    scripts = data["project"]["scripts"]
    assert scripts["decoy"] == "decoy.__main__:app"


def test_classifiers_cover_python_3_10_3_11_3_12() -> None:
    """Release-smoke matrix is Python 3.10/3.11/3.12; classifiers must
    advertise the same versions. A drift here means PyPI's filter shows
    the wrong support tier."""
    data = _load()
    classifiers = set(data["project"]["classifiers"])
    for version in ("3.10", "3.11", "3.12"):
        cls = f"Programming Language :: Python :: {version}"
        assert cls in classifiers, (
            f"Missing Trove classifier {cls!r}; "
            f"release-smoke.yml tests this Python version, the PyPI "
            f"listing must advertise it."
        )


def test_classifiers_marks_development_status_beta() -> None:
    """Pre-1.0: maturity is Beta. A 5+/Stable bump must follow the
    versioning policy at docs/release/versioning.md."""
    data = _load()
    statuses = [c for c in data["project"]["classifiers"] if c.startswith("Development Status ::")]
    assert statuses == ["Development Status :: 4 - Beta"], (
        f"Development status drifted from Beta: {statuses}"
    )


def test_project_urls_present() -> None:
    """PyPI sidebar surfaces these. Missing URLs is a quiet drop in
    listing discoverability."""
    data = _load()
    urls = data["project"]["urls"]
    expected = {"Homepage", "Repository", "Documentation", "Issues", "Changelog"}
    missing = expected - set(urls.keys())
    assert not missing, f"missing project.urls keys: {sorted(missing)}"


def test_keywords_present() -> None:
    """The PyPI search index uses these. An empty keywords list is a
    silent listing-quality regression."""
    data = _load()
    keywords = data["project"]["keywords"]
    assert isinstance(keywords, list) and len(keywords) >= 5, (
        f"keywords list is too short; got {keywords!r}"
    )
    assert "data-masking" in keywords
    assert "decoy" in keywords


def test_engine_dependency_pinned() -> None:
    """The CLI hard-pins the engine release that carries the A-8 token-vault
    seam. A bare or floored `decoy-engine` is a release-process bug: a
    0.7.0-0.14.x engine lacks `token_vault_writer`, so tokenize would TypeError."""
    data = _load()
    deps = data["project"]["dependencies"]
    engine_deps = [d for d in deps if d.startswith("decoy-engine")]
    assert len(engine_deps) == 1, f"expected exactly one decoy-engine dep, got {engine_deps}"
    # Exact pin, shared with the platform vault (B-6); see pyproject.toml.
    from packaging.requirements import Requirement
    from packaging.version import Version

    req = Requirement(engine_deps[0])
    floors = [s for s in req.specifier if s.operator in (">=", "==")]
    # lock_version.sh owns the engine tag, so a repin edits one place and this test follows.
    spec = subprocess.run(
        ["bash", str(PYPROJECT.parent / "scripts" / "dev" / "lock_version.sh"), "--engine-spec"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    pinned = spec.rsplit("@v", 1)[1]
    # 0.7.0-0.14.x lack `token_vault_writer`; a repin below the seam would TypeError in tokenize.
    assert Version(pinned) >= Version("0.15.0"), f"engine pin {pinned} predates token_vault_writer"
    assert [str(s) for s in floors] == [f"=={pinned}"], (
        f"decoy-engine must be pinned exactly =={pinned} (the lock_version.sh engine tag); "
        f"got specifier {str(req.specifier)!r}"
    )


ROOT = PYPROJECT.parent


def test_license_contract_is_fsl_with_both_files_shipped() -> None:
    """One guard for the license contract: SPDX id, the two files the wheel and sdist carry,
    and the license text naming the same id. A drift in any one breaks the legal metadata."""
    project = _load()["project"]
    assert project["license"] == "FSL-1.1-ALv2"
    assert project["license-files"] == ["LICENSE.md", "NOTICE"]
    for name in project["license-files"]:
        assert (ROOT / name).is_file(), f"{name} is listed in license-files but missing"
    first_lines = (ROOT / "LICENSE.md").read_text(encoding="utf-8").splitlines()[:8]
    assert any("FSL-1.1-ALv2" in line for line in first_lines)


# RG-L: the license id and the install story must read the same in every doc a user opens.
LICENSE_DOCS = (
    "LICENSE.md",
    "NOTICE",
    "LICENSING.md",
    "README.md",
    "docs/install.md",
    "docs/release/versioning.md",
)
# Other license ids are legal only in a sentence that states history or conversion. Each
# allowlisted sentence is keyed by (file, full sentence) with its exact occurrence count, so a new
# sentence that reuses an allowed fragment fails. LICENSE.md is the verbatim FSL text, so it is
# only checked for the FSL id. NOTICE here has no vendored third-party table, so it is scanned
# whole.
OTHER_LICENSE_ID = re.compile(
    r"Apache|\bMIT\b|GPL|\bBSD|\bMPL|BUSL|\bBSL|Business Source License|Elastic License"
    r"|SSPL|Server Side Public License|GNU General Public License",
    re.IGNORECASE,
)
_FSL_NAME = "Functional Source License, Version 1.1, Apache 2.0 Future License"
ALLOWED_ID_SENTENCES: dict[str, dict[str, int]] = {
    "NOTICE": {
        f"Licensed under the {_FSL_NAME} (FSL-1.1-ALv2).": 1,
    },
    "LICENSING.md": {
        "Decoy (the `decoy-cli` command-line tool; the `decoy-engine` library and "
        "the `decoy-engine-native` companion from their first FSL release onward) is licensed under "
        f"the **{_FSL_NAME}** (SPDX: `FSL-1.1-ALv2`).": 1,
        "Engine 0.22.0 and earlier stay Apache-2.0; 0.23.0 and later, including the 0.28.2 the CLI "
        "pins today, are FSL-1.1-ALv2.": 1,
        "Each release becomes Apache-2.0 open source two years after it ships.": 1,
        "**What happens after two years?** Each release is automatically licensed under Apache-2.0 "
        "on the second anniversary of the date it was released.": 1,
        "From then on, that release (and only that release) can be used for any purpose, including "
        "a competing one, under Apache-2.0.": 1,
        "Each release becomes open source (Apache-2.0) after two years.": 1,
        "**What about older engine releases that shipped under Apache-2.0?** They keep the license "
        "they shipped with.": 1,
    },
    "README.md": {
        "Each release becomes Apache-2.0 two years after it ships.": 1,
        f"{_FSL_NAME} (FSL-1.1-ALv2).": 1,
        "`decoy-engine` moves to the same license from its first FSL release onward; engine 0.22.0 "
        "and earlier stay Apache-2.0; 0.23.0 and later, including the 0.28.2 this CLI pins today, "
        "are FSL-1.1-ALv2.": 1,
        "Each release converts to the Apache License 2.0 on the second anniversary of its release.": 1,
    },
    "docs/install.md": {},
    "docs/release/versioning.md": {},
}


def _id_sentences(text: str) -> dict[str, int]:
    """Whitespace-normalized sentences that name a license id, with occurrence counts. A new
    markdown block (blank line, heading, bullet) starts a new sentence."""
    blocks: list[list[str]] = [[]]
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith(("#", "- ", "* ", "|")):
            blocks.append([])
        blocks[-1].append(line.strip())
        if line.startswith("#"):
            blocks.append([])
    counts: dict[str, int] = {}
    for block in blocks:
        joined = " ".join(part for part in block if part)
        for sentence in re.split(r"(?<=[.!?;])\s+(?=[A-Z*(`])", joined):
            if OTHER_LICENSE_ID.search(sentence):
                counts[sentence] = counts.get(sentence, 0) + 1
    return counts


def test_one_license_id_across_docs() -> None:
    """AT-L1: every license doc names FSL-1.1-ALv2, and any other license id sits in an
    allowlisted history or conversion sentence, exactly as many times as listed."""
    for name in LICENSE_DOCS:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "FSL-1.1-ALv2" in text, f"{name} does not name FSL-1.1-ALv2"
    for name, allowed in ALLOWED_ID_SENTENCES.items():
        found = _id_sentences((ROOT / name).read_text(encoding="utf-8"))
        assert found == allowed, (
            f"{name}: license-id sentences changed. New or miscounted: "
            f"{ {k: v for k, v in found.items() if allowed.get(k) != v} }; "
            f"missing: {[k for k in allowed if k not in found]}"
        )


def test_versioning_has_no_pypi_or_engine_floor() -> None:
    """AT-L1: versioning.md describes the bundle release and the exact engine pin, never a
    PyPI publish or a `>=` engine floor."""
    text = (ROOT / "docs/release/versioning.md").read_text(encoding="utf-8")
    assert not re.search(r"pypi|trusted[- ]publishing", text, re.IGNORECASE)
    assert not re.search(r"decoy-engine\s*>=", text)
    assert "decoy-engine==" in text
