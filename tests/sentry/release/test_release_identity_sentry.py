"""AT-I2: the release identity is defined once, and every checked copy equals it.

`decoy.distribution.release_identity` holds the repos, site origin and artifact base. This sentry
keeps four things true:

1. Every `github.com/<owner>/<repo>` in the release inputs (the `[project.urls]` table, the
   engine line of `requirements-dev.lock`, both shell installers, the two Python installer
   modules, and the release input and workflow files once they exist) names one of the three
   identity repos. Third-party tool URLs live in `ci/install-policy.toml`, which is not scanned.
2. `installer.DEFAULT_BUNDLE_BASE` equals `ARTIFACT_BASE`, and both shell installer literals
   equal it. `version_document.DEFAULT_URL` equals `SITE_ORIGIN + "/cli/version.json"`.
3. No Python module under `src/`, `scripts/` or `packaging_tools/` other than `release_identity`
   spells an identity string or assigns an identity name (AST).
4. A file named in (1) that does not exist yet is listed in `PENDING` with its owning slice;
   any other missing file fails. When a pending file lands, delete its row.

Findings name a path and a rule, never the matched text. The old org name is spelled in two
pieces so this file does not hold it.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

from decoy.distribution import installer, release_identity, version_document

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[3]
IDENTITY_MODULE = "src/decoy/distribution/release_identity.py"
OLD_ORG = "louis" + "keep"

REPOS = frozenset(
    {release_identity.CLI_REPO, release_identity.ENGINE_REPO, release_identity.WEB_REPO}
)
# Host case-insensitive, an optional trailing dot, and `/` (URL) or `:` (scp-style git) before the
# owner. Owner and repo compare exactly against REPOS.
_REPO_URL = re.compile(
    r"github\.com\.?[/:]([A-Za-z0-9_.-]+)/([A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*)", re.IGNORECASE
)
# Release inputs scanned as whole files. A file that does not exist yet is named in PENDING with
# the slice that creates it; any other missing file fails.
SCANNED = (
    "requirements-dev.lock",
    "packaging_tools/install/install.sh",
    "packaging_tools/install/install.ps1",
    "src/decoy/distribution/installer.py",
    "src/decoy/distribution/version_document.py",
    "packaging_tools/release_inputs.toml",
    ".github/workflows/release.yml",
    # Existing consumers of the engine repo URL: the dev lock profile and two workflow installs.
    "scripts/dev/lock_version.sh",
    ".github/workflows/ci.yml",
    ".github/workflows/release-smoke.yml",
)
CONSUMERS = SCANNED[-3:]
PENDING = {
    "packaging_tools/release_inputs.toml": "S0a1",
    ".github/workflows/release.yml": "S0a2",
    "generated version.json": "S0a2",
    "generated candidate.json": "S0a2",
}
IDENTITY_NAMES = frozenset(
    {
        "CLI_REPO",
        "ENGINE_REPO",
        "WEB_REPO",
        "SITE_ORIGIN",
        "ARTIFACT_BASE",
        "ARTIFACT_HOST_EXCEPTION",
        "WEB_COMMIT_IDENTITY",
    }
)
CODE_ROOTS = ("src", "scripts", "packaging_tools")


def repo_findings(path: str, text: str) -> list[str]:
    out: list[str] = []
    for owner, repo in _REPO_URL.findall(text):
        if repo.endswith(".git"):
            repo = repo[:-4]
        if f"{owner}/{repo}" not in REPOS:
            out.append(f"{path}: a github.com repo outside the three identity repos")
    return out


def project_urls_text() -> str:
    urls = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["urls"]
    return "\n".join(urls.values())


def scanned_texts(root: Path = ROOT) -> dict[str, str]:
    out = {"pyproject.toml [project.urls]": project_urls_text()}
    for rel in SCANNED:
        if (root / rel).is_file():
            out[rel] = (root / rel).read_text(encoding="utf-8")
        else:
            assert rel in PENDING, f"{rel} is scanned but missing and not in PENDING"
    return out


def _forbidden_string(value: str) -> bool:
    return (
        value in REPOS
        or value == release_identity.SITE_ORIGIN
        or value == version_document.DEFAULT_URL
        or value.startswith(release_identity.ARTIFACT_BASE)
    )


def definition_findings(sources: Mapping[str, str]) -> list[str]:
    """A string equal to an identity value, or an assignment to an identity name, outside the module."""
    out: list[str] = []
    for path, source in sorted(sources.items()):
        if path == IDENTITY_MODULE:
            continue
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if _forbidden_string(node.value):
                    out.append(f"{path}:{node.lineno}: an identity string outside release_identity")
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id in IDENTITY_NAMES:
                    out.append(f"{path}:{node.lineno}: a second definition of an identity name")
    return out


def code_sources(root: Path = ROOT) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
        for base in CODE_ROOTS
        for p in sorted((root / base).rglob("*.py"))
    }


def _shell_text(root: Path) -> dict[str, str]:
    return {
        name: (root / "packaging_tools/install" / name).read_text(encoding="utf-8")
        for name in ("install.sh", "install.ps1")
    }


def _one(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    assert match, "installer assignment line not found"
    return match.group(1)


def shell_literals(root: Path = ROOT) -> dict[str, str]:
    """The bundle base each shell installer assigns, read from its assignment line."""
    text = _shell_text(root)
    return {
        "install.sh": _one(r'^DEFAULT_BUNDLE_BASE="([^"]*)"$', text["install.sh"]),
        "install.ps1": _one(r'^\$BundleBase = .*else \{ "([^"]*)" \}$', text["install.ps1"]),
    }


def shell_version_urls(root: Path = ROOT) -> dict[str, str]:
    """The version URL each shell installer assigns, read from its assignment line."""
    text = _shell_text(root)
    return {
        "install.sh": _one(r'^DEFAULT_VERSION_URL="([^"]*)"$', text["install.sh"]),
        "install.ps1": _one(r'^\$VersionUrl = .*else \{ "([^"]*)" \}$', text["install.ps1"]),
    }


def test_every_github_repo_in_release_inputs_is_an_identity_repo():
    out = [f for path, text in scanned_texts().items() for f in repo_findings(path, text)]
    assert out == []


def test_the_scanned_set_includes_the_files_that_exist_today():
    assert {
        "pyproject.toml [project.urls]",
        "requirements-dev.lock",
        *SCANNED[1:5],
        *CONSUMERS,
    } <= set(scanned_texts())


def test_installer_default_equals_the_artifact_base():
    assert installer.DEFAULT_BUNDLE_BASE == release_identity.ARTIFACT_BASE
    assert set(shell_literals().values()) == {release_identity.ARTIFACT_BASE}


def test_default_version_url_is_site_origin_plus_path():
    assert version_document.DEFAULT_URL == release_identity.SITE_ORIGIN + "/cli/version.json"
    assert set(shell_version_urls().values()) == {version_document.DEFAULT_URL}


def test_release_identity_is_the_only_definition():
    assert definition_findings(code_sources()) == []


def test_a_seeded_old_org_copy_fails():
    seeded = f'x = "https://github.com/{OLD_ORG}/decoy/releases/download"\n'
    assert repo_findings("seed.sh", seeded) == [
        "seed.sh: a github.com repo outside the three identity repos"
    ]
    assert repo_findings("seed.sh", f"git+https://github.com/{OLD_ORG}/decoy-engine@abc") != []


def test_a_fork_and_another_repo_fail_and_the_three_pass():
    assert repo_findings("s", "github.com/someone/decoy") != []
    assert repo_findings("s", "github.com/decoy-data/decoy-platform") != []
    for repo in REPOS:
        assert repo_findings("s", f"https://github.com/{repo}.git and github.com/{repo}/x") == []


def test_a_second_definition_fails():
    base = release_identity.ARTIFACT_BASE
    literal = {"mod.py": f'BASE = "{base}"\n'}
    named = {"mod.py": "ARTIFACT_BASE = make()\n"}
    annotated = {"mod.py": "WEB_REPO: str = other\n"}
    assert len(definition_findings(literal)) == 1
    assert len(definition_findings(named)) == 1
    assert len(definition_findings(annotated)) == 1
    assert definition_findings({IDENTITY_MODULE: f'ARTIFACT_BASE = "{base}"\n'}) == []


def test_an_import_of_the_value_is_not_a_second_definition():
    src = "from decoy.distribution import release_identity\nB = release_identity.ARTIFACT_BASE\n"
    assert definition_findings({"mod.py": src}) == []


def _seed_installers(root: Path, base: str, version_url: str) -> None:
    d = root / "packaging_tools/install"
    d.mkdir(parents=True)
    (d / "install.sh").write_text(
        f'DEFAULT_VERSION_URL="{version_url}"\nDEFAULT_BUNDLE_BASE="{base}"\n', encoding="utf-8"
    )
    (d / "install.ps1").write_text(
        f'$VersionUrl = if ($e) {{ $e }} else {{ "{version_url}" }}\n'
        f'$BundleBase = if ($e) {{ $e }} else {{ "{base}" }}\n',
        encoding="utf-8",
    )


def test_seeded_installers_with_the_right_values_agree(tmp_path):
    _seed_installers(tmp_path, release_identity.ARTIFACT_BASE, version_document.DEFAULT_URL)
    assert set(shell_literals(tmp_path).values()) == {release_identity.ARTIFACT_BASE}
    assert set(shell_version_urls(tmp_path).values()) == {version_document.DEFAULT_URL}


def test_a_changed_shell_literal_is_caught_by_the_agreement_check(tmp_path):
    bad_base = f"https://github.com/{OLD_ORG}/decoy/releases/download"
    _seed_installers(tmp_path, bad_base, version_document.DEFAULT_URL + "x")
    assert set(shell_literals(tmp_path).values()) != {release_identity.ARTIFACT_BASE}
    assert set(shell_version_urls(tmp_path).values()) != {version_document.DEFAULT_URL}
    assert repo_findings("install.sh", shell_literals(tmp_path)["install.sh"]) != []


def test_pending_files_are_still_missing_and_name_a_slice():
    for rel, slice_name in PENDING.items():
        assert re.fullmatch(r"S0a[12]", slice_name), rel
        if not rel.startswith("generated "):
            assert not (ROOT / rel).exists(), f"{rel} landed: delete its PENDING row"


@pytest.mark.parametrize(
    "text",
    [
        f"https://{host}{sep}{OLD_ORG}/decoy"
        for host, sep in (
            ("GitHub.com", "/"),
            ("github.com.", "/"),
            ("GITHUB.COM", "/"),
            ("git@github.com", ":"),
            ("git@GitHub.com", ":"),
        )
    ],
)
def test_each_url_spelling_of_a_foreign_repo_is_seeded_red(text):
    assert repo_findings("seed", text) != []


def test_each_url_spelling_of_an_identity_repo_is_green():
    for repo in REPOS:
        for text in (
            f"https://GitHub.com/{repo}",
            f"https://github.com./{repo}",
            f"git@github.com:{repo}.git",
        ):
            assert repo_findings("seed", text) == [], text


@pytest.mark.parametrize("rel", CONSUMERS)
def test_each_release_consumer_is_scanned_and_names_the_engine_repo(rel):
    text = scanned_texts()[rel]
    assert repo_findings(rel, text) == []
    assert f"github.com/{release_identity.ENGINE_REPO}@" in text


@pytest.mark.parametrize("rel", CONSUMERS)
def test_a_seeded_foreign_repo_in_each_release_consumer_is_red(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    seeded = text.replace(release_identity.ENGINE_REPO, f"{OLD_ORG}/decoy-engine")
    assert seeded != text
    assert repo_findings(rel, seeded) != []
    forked = text.replace(release_identity.ENGINE_REPO, "someone/decoy-engine")
    assert repo_findings(rel, forked) != []
