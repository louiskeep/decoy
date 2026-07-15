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
    statuses = [c for c in data["project"]["classifiers"]
                if c.startswith("Development Status ::")]
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
    """The CLI declares the minimum engine version it was tested against.
    A bare `decoy-engine` with no version (or downgrading the floor) is
    a release-process bug."""
    data = _load()
    deps = data["project"]["dependencies"]
    engine_deps = [d for d in deps if d.startswith("decoy-engine")]
    assert len(engine_deps) == 1, (
        f"expected exactly one decoy-engine dep, got {engine_deps}"
    )
    # Assert the exact minimum, not merely that *a* floor exists -- a bare
    # `>=` check would let a silent downgrade (e.g. `decoy-engine>=0.1.0`)
    # slip through. 0.4.0 is DE-02's release marker: the first engine version
    # guaranteed to carry `decoy_engine.keyprovider` (see the pin rationale in
    # pyproject.toml). Bump this in lockstep when the floor legitimately rises.
    from packaging.requirements import Requirement

    req = Requirement(engine_deps[0])
    floors = [s for s in req.specifier if s.operator in (">=", "==")]
    assert [str(s) for s in floors] == [">=0.4.0"], (
        f"decoy-engine floor must be exactly >=0.4.0 (DE-02 keyprovider "
        f"marker); got specifier {str(req.specifier)!r}"
    )
