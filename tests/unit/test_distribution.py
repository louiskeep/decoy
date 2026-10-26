"""Unit tests for the CLI distribution + update machinery (`decoy.distribution`).

Covers the shipped verification + install logic without the full ~600 MB managed
bundle (the real bundle, native self-check, and deterministic build are exercised by
the end-to-end smoke, packaging_tools/smoke_install.py):

- signing: detached Ed25519 verify + the pinned-key / tamper / wrong-key cases;
- manifest: file + symlink entries, the forward + reverse walk, tamper detection,
  __pycache__ exclusion, and symlink-escape rejection;
- version_document: canonical round-trip, PEP 440 ordering, yank/floor logic, and
  graceful degradation on unparseable / foreign documents;
- targets + layout: host->target mapping and the atomic current-symlink swap;
- installer: a synthetic signed bundle driven through install_version -- happy path,
  bad bundle signature, checksum mismatch, bad version-document signature, and the
  post-swap rollback;
- release_key: the placeholder build refuses rather than trusting an unfilled key.
"""

from __future__ import annotations

import base64
import gzip
import io
import json
import os
import sys
import tarfile
from pathlib import Path

import pytest
import typer
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from decoy.distribution import (
    installer,
    layout,
    release_key,
    signing,
    targets,
    verify_extracted,
)
from decoy.distribution import (
    manifest as manifest_mod,
)
from decoy.distribution import (
    version_document as vd,
)

# tests/unit/test_distribution.py -> repo root (for packaging_tools, not pip-installed).
REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- keys
@pytest.fixture
def keypair():
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return key, pub


def _sign_b64(key: Ed25519PrivateKey, data: bytes) -> str:
    return base64.b64encode(key.sign(data)).decode("ascii")


@pytest.fixture(autouse=True)
def _isolate_launcher_paths(tmp_path, monkeypatch):
    """Isolate the managed-runtime home AND the launcher dir into this test's tmp_path for
    EVERY test, so no installer test writes to the real ~/.decoy or ~/.local/bin. Prior
    installer tests isolated DECOY_HOME but not DECOY_BIN_DIR, so running the suite wrote a
    real ~/.local/bin/decoy shim pointing into a pytest temp dir. A test may still override
    DECOY_HOME to a sub-path (its own setenv runs after this fixture and wins); the
    launcher dir is always confined here regardless."""
    monkeypatch.setenv("DECOY_HOME", str(tmp_path / "_managed_home"))
    monkeypatch.setenv("DECOY_BIN_DIR", str(tmp_path / "_managed_bin"))


# ------------------------------------------------------------------------- signing
def test_verify_detached_roundtrip_and_tamper(keypair):
    key, pub = keypair
    data = b'{"latest":"0.1.0"}'
    sig = _sign_b64(key, data)
    assert signing.verify_detached(data, sig, expected_public_pem=pub) is True
    assert signing.verify_detached(data + b"x", sig, expected_public_pem=pub) is False


def test_verify_detached_wrong_key_rejected(keypair):
    key, _ = keypair
    other = Ed25519PrivateKey.generate()
    other_pub = other.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    data = b"payload"
    sig = _sign_b64(key, data)
    assert signing.verify_detached(data, sig, expected_public_pem=other_pub) is False


def test_verify_detached_garbage_never_raises(keypair):
    _, pub = keypair
    assert signing.verify_detached(b"x", "not-base64!!", expected_public_pem=pub) is False
    assert signing.verify_detached(b"x", "", expected_public_pem="not a pem") is False


def test_verify_envelope_schema_and_alg(keypair):
    key, pub = keypair
    payload = {"schema_version": "t/v1", "a": 1}
    env = {
        "alg": "ed25519",
        "payload": payload,
        "signature": _sign_b64(key, signing.canonical_bytes(payload)),
        "public_key": pub,
    }
    assert signing.verify_envelope(env, expected_public_pem=pub, schema_version="t/v1")
    assert not signing.verify_envelope(env, expected_public_pem=pub, schema_version="other/v1")
    env["alg"] = "rsa"
    assert not signing.verify_envelope(env, expected_public_pem=pub, schema_version="t/v1")


# ------------------------------------------------------------------------ manifest
def _make_tree(root: Path) -> None:
    (root / "python" / "bin").mkdir(parents=True)
    (root / "python" / "bin" / "python3.12").write_text("#!/bin/sh\necho hi\n")
    (root / "python" / "bin" / "python3").symlink_to("python3.12")  # internal symlink
    (root / "decoy").write_text("#!/bin/sh\n")
    (root / "BUNDLE_INFO.json").write_text("{}")


def test_manifest_roundtrip_files_and_symlinks(tmp_path):
    root = tmp_path / "b"
    root.mkdir()
    _make_tree(root)
    man = manifest_mod.compute_manifest(root, version="0.1.0", target="linux-x86_64")
    paths = {e["path"]: e for e in man["files"]}
    assert paths["python/bin/python3"]["type"] == "link"
    assert paths["python/bin/python3"]["target"] == "python3.12"
    assert "sha256" in paths["python/bin/python3.12"]
    assert manifest_mod.verify_manifest(man, root) == []


def test_manifest_detects_content_tamper(tmp_path):
    root = tmp_path / "b"
    root.mkdir()
    _make_tree(root)
    man = manifest_mod.compute_manifest(root, version="0.1.0", target="t")
    # same length, different content -> caught by the hash (not the size shortcut)
    assert (root / "decoy").read_text() == "#!/bin/sh\n"
    (root / "decoy").write_text("#!/bin/xx\n")
    problems = manifest_mod.verify_manifest(man, root)
    assert any(p["path"] == "decoy" and p["problem"] == "hash" for p in problems)


def test_manifest_rejects_bytecode_cache_and_unexpected(tmp_path):
    root = tmp_path / "b"
    root.mkdir()
    _make_tree(root)
    man = manifest_mod.compute_manifest(root, version="0.1.0", target="t")
    # A correct bundle ships no caches and the manifest signs none.
    assert manifest_mod.verify_manifest(man, root) == []
    # A __pycache__ planted after signing is NOT benign: Python's timestamp-based
    # invalidation would load a forged .pyc in place of the signed source, so verify
    # must REJECT it (the HIGH-1 "verify-clean, execute-forged" bypass).
    pc = root / "python" / "lib" / "__pycache__"
    pc.mkdir(parents=True)
    (pc / "mod.cpython-312.pyc").write_bytes(b"bytecode")
    problems = manifest_mod.verify_manifest(man, root)
    assert any(p["path"] == "python/lib/__pycache__" and p["problem"] == "bytecode-cache" for p in problems)
    # A stray .pyc outside __pycache__ is rejected too.
    (root / "python" / "stray.pyc").write_bytes(b"bytecode")
    problems = manifest_mod.verify_manifest(man, root)
    assert any(p["path"] == "python/stray.pyc" and p["problem"] == "bytecode-cache" for p in problems)
    # a real unexpected file IS still flagged
    (root / "python" / "planted.so").write_bytes(b"x")
    problems = manifest_mod.verify_manifest(man, root)
    assert any(p["problem"] == "unexpected" for p in problems)


def test_manifest_rejects_escaping_symlink_at_build(tmp_path):
    root = tmp_path / "b"
    root.mkdir()
    (root / "evil").symlink_to("../../etc/passwd")
    with pytest.raises(ValueError, match="escapes root"):
        manifest_mod.compute_manifest(root, version="0.1.0", target="t")


def test_symlink_escape_predicate():
    esc = manifest_mod._symlink_target_escapes
    assert esc("python/bin/python3", "python3.12") is False
    assert esc("a/b/c", "../d") is False  # stays under root
    assert esc("a/b", "../../etc/passwd") is True
    assert esc("x", "/abs/path") is True


# ----------------------------------------------------------------- version_document
def test_version_document_canonical_and_select(keypair):
    doc = vd.build_document(
        latest="0.2.0", min_supported="0.1.0",
        artifacts={"linux-x86_64": {"url": "u", "sha256": "h", "sig": "s"}},
        yanked=["0.0.9"], generated="2026-01-01T00:00:00Z",
    )
    data = vd.canonical_document_bytes(doc)
    assert vd.parse_document(data)["latest"] == "0.2.0"
    assert vd.select_artifact(doc, "linux-x86_64") == {"url": "u", "sha256": "h", "sig": "s"}
    assert vd.select_artifact(doc, "macos-arm64") is None


def test_version_document_pep440_and_flags():
    doc = vd.build_document(latest="0.10.0", min_supported="0.2.0", artifacts={}, yanked=["0.10.1"])
    assert vd.compare_versions("0.2.0", "0.10.0") == -1
    assert vd.newer_available("0.9.0", doc) is True
    assert vd.newer_available("0.10.0", doc) is False
    assert vd.below_floor("0.1.0", doc) is True
    assert vd.below_floor("0.2.0", doc) is False
    # yanked latest -> no upgrade offered
    doc2 = vd.build_document(latest="0.10.1", min_supported="0.2.0", artifacts={}, yanked=["0.10.1"])
    assert vd.newer_available("0.9.0", doc2) is False


def test_version_document_degrades_on_garbage():
    doc = vd.build_document(latest="not-a-version", min_supported="x", artifacts={})
    assert vd.newer_available("0.1.0", doc) is False  # does not raise
    with pytest.raises(ValueError):
        vd.parse_document(b'{"schema_version":"other/v9"}')


# -------------------------------------------------------------------------- targets
@pytest.mark.parametrize(
    "system,machine,expected",
    [
        ("Linux", "x86_64", "linux-x86_64"),
        ("Linux", "amd64", "linux-x86_64"),
        ("Linux", "aarch64", "linux-aarch64"),
        ("Darwin", "arm64", "macos-arm64"),
        ("Darwin", "x86_64", None),  # Intel mac unsupported at launch
        ("Windows", "AMD64", None),  # Windows gated off the advertised matrix this cycle
        ("Linux", "riscv64", None),
    ],
)
def test_detect_target(system, machine, expected):
    assert targets.detect_target(system, machine) == expected


# --------------------------------------------------------------------------- layout
def test_atomic_point_current_and_read(tmp_path, monkeypatch):
    monkeypatch.setenv("DECOY_HOME", str(tmp_path))
    (layout.versions_dir() / "0.1.0").mkdir(parents=True)
    (layout.versions_dir() / "0.2.0").mkdir(parents=True)
    layout.atomic_point_current_at("0.1.0")
    assert layout.read_current_version() == "0.1.0"
    layout.atomic_point_current_at("0.2.0")  # retarget in place
    assert layout.read_current_version() == "0.2.0"
    assert os.readlink(layout.current_link()) == os.path.join("versions", "0.2.0")


# ------------------------------------------------------------------------ selfcheck
def test_selfcheck_ok_and_refuse(monkeypatch):
    from decoy.distribution import selfcheck

    class _Status:
        ok = True
        present = True
        version = "0.1.0"
        abi_expected = "decoy-native-abi-3"
        abi_actual = "decoy-native-abi-3"
        reason = "present-ok"

    import types

    fake = types.SimpleNamespace(native_companion_status=lambda: _Status())
    monkeypatch.setitem(__import__("sys").modules, "decoy_engine", fake)
    assert selfcheck.check_native_present().ok is True

    _Status.ok = False
    _Status.present = False
    _Status.reason = "companion-absent"
    assert selfcheck.check_native_present().ok is False


# ------------------------------------------------------------------- release_key
def test_release_key_placeholder_refuses(monkeypatch):
    monkeypatch.delenv("DECOY_RELEASE_PUBKEY_FILE", raising=False)
    # The committed key is a placeholder in a dev checkout.
    with pytest.raises(release_key.NoPinnedKeyError):
        release_key.pinned_public_pem()


def test_release_key_override(tmp_path, monkeypatch, keypair):
    _, pub = keypair
    p = tmp_path / "k.pem"
    p.write_text(pub)
    monkeypatch.setenv("DECOY_RELEASE_PUBKEY_FILE", str(p))
    assert release_key.pinned_public_pem() == pub


# ------------------------------------------------------------------------- installer
def _deterministic_targz(stage: Path, out_path: Path) -> None:
    top = out_path.name[: -len(".tar.gz")]
    raw = io.BytesIO()
    members = sorted(stage.rglob("*"), key=lambda x: x.relative_to(stage).as_posix())
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for p in members:
            ti = tar.gettarinfo(str(p), arcname=f"{top}/{p.relative_to(stage).as_posix()}")
            ti.mtime = 1700000000
            ti.uid = ti.gid = 0
            if p.is_symlink():
                tar.addfile(ti)
            elif p.is_file():
                with open(p, "rb") as fh:
                    tar.addfile(ti, fh)
            else:
                tar.addfile(ti)
    with open(out_path, "wb") as fh:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0) as gz:
            gz.write(raw.getvalue())


def _synthetic_release(tmp_path: Path, key: Ed25519PrivateKey, pub: str, version: str = "0.1.0"):
    """Build a tiny signed bundle + a signed version document served from local files."""
    stage = tmp_path / f"decoy-{version}-linux-x86_64"
    stage.mkdir(parents=True)
    _make_tree(stage)
    man = manifest_mod.compute_manifest(stage, version=version, target="linux-x86_64")
    man_bytes = signing.canonical_bytes(man)
    (stage / manifest_mod.MANIFEST_NAME).write_bytes(man_bytes)
    (stage / manifest_mod.MANIFEST_SIG_NAME).write_text(_sign_b64(key, man_bytes))

    serve = tmp_path / "serve"
    serve.mkdir()
    tarball = serve / f"decoy-{version}-linux-x86_64.tar.gz"
    _deterministic_targz(stage, tarball)
    tar_bytes = tarball.read_bytes()
    sha = manifest_mod.sha256_bytes(tar_bytes)
    sig_b64 = _sign_b64(key, tar_bytes)
    (serve / (tarball.name + ".sig")).write_text(sig_b64)

    doc = vd.build_document(
        latest=version, min_supported=version,
        artifacts={"linux-x86_64": {
            "url": f"file://{tarball}", "sha256": sha, "sig": f"file://{tarball}.sig",
        }},
    )
    doc_bytes = vd.canonical_document_bytes(doc)
    doc_sig = _sign_b64(key, doc_bytes)

    def download(url: str) -> bytes:
        path = url[len("file://"):]
        return Path(path).read_bytes()

    return doc_bytes, doc_sig, download, tar_bytes, sha


def test_installer_happy_path(tmp_path, monkeypatch, keypair):
    key, pub = keypair
    monkeypatch.setenv("DECOY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DECOY_BIN_DIR", str(tmp_path / "bin"))
    doc_bytes, doc_sig, download, *_ = _synthetic_release(tmp_path, key, pub)

    outcome = installer.install_version(
        version_doc_bytes=doc_bytes, version_doc_sig_b64=doc_sig,
        expected_public_pem=pub, target="linux-x86_64",
        home=layout.decoy_home(), download=download,
        run_self_check=False, post_swap_validate=lambda cur: True,
    )
    assert outcome.version == "0.1.0"
    assert layout.read_current_version() == "0.1.0"
    assert (layout.version_dir("0.1.0") / "decoy").exists()
    assert (tmp_path / "bin" / "decoy").exists()


def test_installer_rejects_bad_bundle_signature(tmp_path, monkeypatch, keypair):
    key, pub = keypair
    monkeypatch.setenv("DECOY_HOME", str(tmp_path / "home"))
    doc_bytes, doc_sig, download, tar_bytes, _sha = _synthetic_release(tmp_path, key, pub)
    # Corrupt the served tarball so its signature no longer matches.
    bad = tmp_path / "serve" / "decoy-0.1.0-linux-x86_64.tar.gz"
    bad.write_bytes(tar_bytes[:-1] + bytes([tar_bytes[-1] ^ 0xFF]))

    with pytest.raises(installer.InstallError, match=r"signature invalid|checksum mismatch"):
        installer.install_version(
            version_doc_bytes=doc_bytes, version_doc_sig_b64=doc_sig,
            expected_public_pem=pub, target="linux-x86_64",
            home=layout.decoy_home(), download=download, run_self_check=False,
        )


def test_installer_rejects_checksum_mismatch(tmp_path, monkeypatch, keypair):
    key, pub = keypair
    monkeypatch.setenv("DECOY_HOME", str(tmp_path / "home"))
    # Hand-build a document whose declared sha256 is wrong but still signed.
    serve = tmp_path / "serve"
    serve.mkdir()
    stage = tmp_path / "decoy-0.1.0-linux-x86_64"
    stage.mkdir()
    _make_tree(stage)
    man = manifest_mod.compute_manifest(stage, version="0.1.0", target="linux-x86_64")
    (stage / manifest_mod.MANIFEST_NAME).write_bytes(signing.canonical_bytes(man))
    tarball = serve / "decoy-0.1.0-linux-x86_64.tar.gz"
    _deterministic_targz(stage, tarball)
    (serve / (tarball.name + ".sig")).write_text(_sign_b64(key, tarball.read_bytes()))
    doc = vd.build_document(
        latest="0.1.0", min_supported="0.1.0",
        artifacts={"linux-x86_64": {"url": f"file://{tarball}", "sha256": "0" * 64, "sig": f"file://{tarball}.sig"}},
    )
    doc_bytes = vd.canonical_document_bytes(doc)
    doc_sig = _sign_b64(key, doc_bytes)

    def download(url: str) -> bytes:
        return Path(url[len("file://"):]).read_bytes()

    with pytest.raises(installer.InstallError, match="checksum mismatch"):
        installer.install_version(
            version_doc_bytes=doc_bytes, version_doc_sig_b64=doc_sig,
            expected_public_pem=pub, target="linux-x86_64",
            home=layout.decoy_home(), download=download, run_self_check=False,
        )


def test_installer_rejects_bad_document_signature(tmp_path, monkeypatch, keypair):
    key, pub = keypair
    monkeypatch.setenv("DECOY_HOME", str(tmp_path / "home"))
    doc_bytes, doc_sig, download, *_ = _synthetic_release(tmp_path, key, pub)
    other = Ed25519PrivateKey.generate()
    other_pub = other.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    with pytest.raises(installer.InstallError, match="version-document signature invalid"):
        installer.install_version(
            version_doc_bytes=doc_bytes, version_doc_sig_b64=doc_sig,
            expected_public_pem=other_pub, target="linux-x86_64",
            home=layout.decoy_home(), download=download, run_self_check=False,
        )


def test_installer_rolls_back_on_post_swap_failure(tmp_path, monkeypatch, keypair):
    key, pub = keypair
    home = tmp_path / "home"
    monkeypatch.setenv("DECOY_HOME", str(home))
    monkeypatch.setenv("DECOY_BIN_DIR", str(tmp_path / "bin"))

    # install v1 cleanly
    d1, s1, dl1, *_ = _synthetic_release(tmp_path / "v1", key, pub, version="0.1.0")
    installer.install_version(
        version_doc_bytes=d1, version_doc_sig_b64=s1, expected_public_pem=pub,
        target="linux-x86_64", home=layout.decoy_home(), download=dl1,
        run_self_check=False, post_swap_validate=lambda cur: True,
    )
    assert layout.read_current_version() == "0.1.0"

    # install v2 but fail the post-swap validation -> rollback to v1
    d2, s2, dl2, *_ = _synthetic_release(tmp_path / "v2", key, pub, version="0.2.0")
    with pytest.raises(installer.InstallError, match="rolled back"):
        installer.install_version(
            version_doc_bytes=d2, version_doc_sig_b64=s2, expected_public_pem=pub,
            target="linux-x86_64", home=layout.decoy_home(), download=dl2,
            run_self_check=False, post_swap_validate=lambda cur: False,
        )
    assert layout.read_current_version() == "0.1.0"  # rolled back
    assert layout.version_dir("0.2.0").exists()  # new runtime kept for inspection


def test_upgrade_managed_home_detection(monkeypatch):
    """`decoy upgrade` recognizes a managed runtime by its own interpreter prefix
    (<home>/versions/<ver>/python), independent of DECOY_HOME, and refuses a pip/dev
    install (no `versions` ancestor)."""
    from decoy.cli import upgrade

    monkeypatch.setattr(sys, "prefix", "/opt/x/.decoy/versions/0.3.0/python")
    assert upgrade._managed_home() == Path("/opt/x/.decoy")
    monkeypatch.setattr(sys, "prefix", "/usr")
    assert upgrade._managed_home() is None


def test_verify_extracted_flags_problems(tmp_path, keypair):
    key, pub = keypair
    stage = tmp_path / "decoy-0.1.0-linux-x86_64"
    stage.mkdir()
    _make_tree(stage)
    man = manifest_mod.compute_manifest(stage, version="0.1.0", target="linux-x86_64")
    man_bytes = signing.canonical_bytes(man)
    (stage / manifest_mod.MANIFEST_NAME).write_bytes(man_bytes)
    (stage / manifest_mod.MANIFEST_SIG_NAME).write_text(_sign_b64(key, man_bytes))
    assert verify_extracted.verify_extracted(stage, expected_public_pem=pub) == []
    # tamper a file -> problem reported
    (stage / "decoy").write_text("tampered")
    assert verify_extracted.verify_extracted(stage, expected_public_pem=pub)


# ------------------------------------------- pinned-version resolution + rollback (B2)
def _serve_bundle(
    serve_dir: Path,
    version: str,
    key: Ed25519PrivateKey,
    *,
    declared: str | None = None,
    declared_target: str = "linux-x86_64",
) -> str:
    """Build a signed bundle for ``version`` at serve_dir/<version>/ and return its file://
    URL. ``declared`` overrides the version the bundle DECLARES and ``declared_target`` the
    target it DECLARES (to simulate a resolution mismatch where the bytes served at one
    version/target path actually belong to another)."""
    dv = declared or version
    stage = serve_dir / f"_stage-{version}" / f"decoy-{version}-linux-x86_64"
    stage.mkdir(parents=True)
    _make_tree(stage)
    (stage / "BUNDLE_INFO.json").write_text(
        json.dumps({"schema_version": "cli-bundle-info/v1", "version": dv, "target": declared_target})
    )
    man = manifest_mod.compute_manifest(stage, version=dv, target=declared_target)
    mb = signing.canonical_bytes(man)
    (stage / manifest_mod.MANIFEST_NAME).write_bytes(mb)
    (stage / manifest_mod.MANIFEST_SIG_NAME).write_text(_sign_b64(key, mb))
    vdir = serve_dir / version
    vdir.mkdir(parents=True, exist_ok=True)
    tarball = vdir / f"decoy-{version}-linux-x86_64.tar.gz"
    _deterministic_targz(stage, tarball)
    (tarball.with_name(tarball.name + ".sha256")).write_text(
        f"{manifest_mod.sha256_file(tarball)}  {tarball.name}\n"
    )
    (tarball.with_name(tarball.name + ".sig")).write_text(_sign_b64(key, tarball.read_bytes()))
    return f"file://{tarball}"


def _file_download(url: str) -> bytes:
    return Path(url[len("file://"):]).read_bytes()


def _doc_for_latest(serve_dir: Path, latest: str, latest_url: str, key: Ed25519PrivateKey):
    doc = vd.build_document(
        latest=latest, min_supported="0.1.0",
        artifacts={"linux-x86_64": {
            "url": latest_url,
            "sha256": manifest_mod.sha256_bytes(_file_download(latest_url)),
            "sig": latest_url + ".sig",
        }},
    )
    data = vd.canonical_document_bytes(doc)
    return data, _sign_b64(key, data)


def test_installer_pin_older_installs_real_older_bits(tmp_path, monkeypatch, keypair):
    """`decoy upgrade --version <older>` against a doc whose latest is newer installs the
    REAL older bundle (resolved by URL convention), not the latest bits mislabeled."""
    key, pub = keypair
    monkeypatch.setenv("DECOY_HOME", str(tmp_path / "home"))
    serve = tmp_path / "serve"
    latest_url = _serve_bundle(serve, "0.2.0", key)
    _serve_bundle(serve, "0.1.0", key)
    doc_bytes, doc_sig = _doc_for_latest(serve, "0.2.0", latest_url, key)

    outcome = installer.install_version(
        version_doc_bytes=doc_bytes, version_doc_sig_b64=doc_sig, expected_public_pem=pub,
        target="linux-x86_64", home=layout.decoy_home(), pin_version="0.1.0",
        base_url=f"file://{serve}", download=_file_download, run_self_check=False,
        post_swap_validate=lambda cur: True,
    )
    assert outcome.version == "0.1.0"
    installed = layout.version_dir("0.1.0")
    declared = json.loads((installed / "BUNDLE_INFO.json").read_text())["version"]
    assert declared == "0.1.0"  # the REAL older bits, not latest mislabeled


def test_installer_pin_version_mismatch_refuses_without_touching_dest(tmp_path, monkeypatch, keypair):
    """If resolution yields a bundle that declares a different version than requested, the
    install refuses BEFORE the destructive rmtree, leaving versions/<version> intact (the
    retained rollback runtime is never destroyed)."""
    key, pub = keypair
    monkeypatch.setenv("DECOY_HOME", str(tmp_path / "home"))
    serve = tmp_path / "serve"
    latest_url = _serve_bundle(serve, "0.2.0", key)
    # Serve bits at the 0.1.0 path that DECLARE 0.2.0 (the mismatch the guard must catch).
    _serve_bundle(serve, "0.1.0", key, declared="0.2.0")
    doc_bytes, doc_sig = _doc_for_latest(serve, "0.2.0", latest_url, key)

    # Pre-seed the retained previous runtime with a sentinel that must survive.
    dest = layout.version_dir("0.1.0")
    dest.mkdir(parents=True)
    sentinel = dest / "KEEP_ME"
    sentinel.write_text("real 0.1.0 runtime")

    with pytest.raises(installer.InstallError, match="declares version"):
        installer.install_version(
            version_doc_bytes=doc_bytes, version_doc_sig_b64=doc_sig, expected_public_pem=pub,
            target="linux-x86_64", home=layout.decoy_home(), pin_version="0.1.0",
            base_url=f"file://{serve}", download=_file_download, run_self_check=False,
        )
    assert sentinel.exists() and sentinel.read_text() == "real 0.1.0 runtime"


def test_activate_local_version_is_a_swap_not_a_download(tmp_path, monkeypatch, keypair):
    """The rollback path: activate an already-installed version via an atomic swap, with
    no download, leaving the other version's dir intact."""
    key, pub = keypair
    monkeypatch.setenv("DECOY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DECOY_BIN_DIR", str(tmp_path / "bin"))
    serve = tmp_path / "serve"
    for v in ("0.1.0", "0.2.0"):
        url = _serve_bundle(serve, v, key)
        doc_bytes, doc_sig = _doc_for_latest(serve, v, url, key)
        installer.install_version(
            version_doc_bytes=doc_bytes, version_doc_sig_b64=doc_sig, expected_public_pem=pub,
            target="linux-x86_64", home=layout.decoy_home(), download=_file_download,
            run_self_check=False, post_swap_validate=lambda cur: True,
        )
    assert layout.read_current_version() == "0.2.0"
    assert installer.local_version_present("0.1.0", layout.decoy_home())

    outcome = installer.activate_local_version(
        "0.1.0", home=layout.decoy_home(), expected_public_pem=pub, run_self_check=False
    )
    assert outcome.version == "0.1.0"
    assert layout.read_current_version() == "0.1.0"
    assert layout.version_dir("0.2.0").is_dir()  # the version we rolled back FROM is kept


# -------------------------------------------------------- HIGH 1: bytecode cache bypass
def test_activate_local_refuses_forged_bytecode_cache(tmp_path, monkeypatch, keypair):
    """A retained runtime with a substituted ``.pyc`` must REFUSE activation. Python's
    timestamp-based cache invalidation would otherwise load the forged bytecode in place
    of the signed source, so `verify_extracted` (which now rejects any cache on disk)
    makes activation fail closed instead of running substituted bytecode."""
    key, pub = keypair
    monkeypatch.setenv("DECOY_HOME", str(tmp_path / "home"))
    serve = tmp_path / "serve"
    url = _serve_bundle(serve, "0.1.0", key)
    doc_bytes, doc_sig = _doc_for_latest(serve, "0.1.0", url, key)
    installer.install_version(
        version_doc_bytes=doc_bytes, version_doc_sig_b64=doc_sig, expected_public_pem=pub,
        target="linux-x86_64", home=layout.decoy_home(), download=_file_download,
        run_self_check=False, post_swap_validate=lambda cur: True,
    )
    dest = layout.version_dir("0.1.0")
    # Substitute a forged bytecode cache into the retained runtime (the signed source is
    # left untouched -- the exact bypass the Codex gate reproduced).
    pc = dest / "python" / "lib" / "__pycache__"
    pc.mkdir(parents=True)
    (pc / "evil.cpython-312.pyc").write_bytes(b"forged bytecode")
    with pytest.raises(installer.InstallError, match=r"verification|bytecode-cache"):
        installer.activate_local_version(
            "0.1.0", home=layout.decoy_home(), expected_public_pem=pub, run_self_check=False
        )


# ------------------------------------------- HIGH 2: wrong-version/target replacement
def test_installer_target_mismatch_refuses_without_touching_dest(tmp_path, monkeypatch, keypair):
    """A validly-signed bundle for ANOTHER platform served at this target's URL must be
    refused BEFORE any deletion, leaving the retained versions/<version> intact."""
    key, pub = keypair
    monkeypatch.setenv("DECOY_HOME", str(tmp_path / "home"))
    serve = tmp_path / "serve"
    # Bytes served at the linux-x86_64 slot that DECLARE linux-aarch64.
    url = _serve_bundle(serve, "0.1.0", key, declared_target="linux-aarch64")
    doc_bytes, doc_sig = _doc_for_latest(serve, "0.1.0", url, key)
    dest = layout.version_dir("0.1.0")
    dest.mkdir(parents=True)
    (dest / "KEEP_ME").write_text("real 0.1.0 runtime")
    with pytest.raises(installer.InstallError, match="declares target"):
        installer.install_version(
            version_doc_bytes=doc_bytes, version_doc_sig_b64=doc_sig, expected_public_pem=pub,
            target="linux-x86_64", home=layout.decoy_home(), download=_file_download,
            run_self_check=False,
        )
    assert (dest / "KEEP_ME").read_text() == "real 0.1.0 runtime"


def test_install_sh_refuses_wrong_version_without_touching_dest(tmp_path, keypair):
    """The SHELL installer (install.sh) must enforce the same identity check: a signed
    bundle that DECLARES a different version than requested is refused before the
    destructive promotion, leaving the pre-seeded versions/<version> intact. Driven over
    the offline (DECOY_LOCAL_BUNDLE) path so it needs no network/proxy."""
    import subprocess as sp

    key, pub = keypair
    work = tmp_path / "w"
    work.mkdir()
    # A signed bundle DECLARING 0.2.0, but we will request --version 0.1.0.
    stage = work / "decoy-0.1.0-linux-x86_64"
    stage.mkdir()
    _make_tree(stage)
    # The interpreter must be executable for install.sh's `[ -x ]` guard + self-check.
    (stage / "python" / "bin" / "python3.12").chmod(0o755)
    # Canonical (compact) JSON: install.sh reads BUNDLE_INFO with a grep that expects the
    # compact "key":"value" form the build writes.
    (stage / "BUNDLE_INFO.json").write_bytes(
        signing.canonical_bytes({"schema_version": "cli-bundle-info/v1", "version": "0.2.0", "target": "linux-x86_64"})
    )
    man = manifest_mod.compute_manifest(stage, version="0.2.0", target="linux-x86_64")
    mb = signing.canonical_bytes(man)
    (stage / manifest_mod.MANIFEST_NAME).write_bytes(mb)
    (stage / manifest_mod.MANIFEST_SIG_NAME).write_text(_sign_b64(key, mb))
    tarball = work / "decoy-0.1.0-linux-x86_64.tar.gz"
    _deterministic_targz(stage, tarball)
    tarball.with_name(tarball.name + ".sha256").write_text(
        f"{manifest_mod.sha256_file(tarball)}  {tarball.name}\n"
    )
    tarball.with_name(tarball.name + ".sig").write_text(_sign_b64(key, tarball.read_bytes()))

    pub_pem = work / "pub.pem"
    pub_pem.write_text(pub)
    home = work / "home"
    dest = home / "versions" / "0.1.0"
    dest.mkdir(parents=True)
    (dest / "KEEP_ME").write_text("real 0.1.0 runtime")

    install_sh = REPO_ROOT / "packaging_tools" / "install" / "install.sh"
    env = dict(os.environ, DECOY_HOME=str(home), DECOY_BIN_DIR=str(work / "bin"),
               DECOY_RELEASE_PUBKEY_FILE=str(pub_pem), DECOY_LOCAL_BUNDLE=str(tarball))
    r = sp.run(["sh", str(install_sh), "--version", "0.1.0"], env=env, capture_output=True, text=True)
    assert r.returncode != 0, r.stdout + r.stderr
    assert "declares version" in r.stderr
    assert (dest / "KEEP_ME").read_text() == "real 0.1.0 runtime"  # untouched


# ------------------------------------------- HIGH 3: same-version reinstall rollback safety
def test_same_version_force_post_swap_failure_preserves_runtime(tmp_path, monkeypatch, keypair):
    """A same-version forced reinstall whose post-swap validation FAILS must restore the
    ORIGINAL runtime bits (not leave the user on the unvalidated replacement, and not a
    missing runtime). The original is retained until validation passes."""
    key, pub = keypair
    monkeypatch.setenv("DECOY_HOME", str(tmp_path / "home"))
    serve = tmp_path / "serve"
    url = _serve_bundle(serve, "0.1.0", key)
    doc_bytes, doc_sig = _doc_for_latest(serve, "0.1.0", url, key)
    installer.install_version(
        version_doc_bytes=doc_bytes, version_doc_sig_b64=doc_sig, expected_public_pem=pub,
        target="linux-x86_64", home=layout.decoy_home(), download=_file_download,
        run_self_check=False, post_swap_validate=lambda cur: True,
    )
    dest = layout.version_dir("0.1.0")
    (dest / "LIVE_MARK").write_text("original live 0.1.0")  # marks the original bits

    # Forced same-version reinstall (dest exists); post-swap fails -> restore original.
    with pytest.raises(installer.InstallError, match=r"rolled back|intact"):
        installer.install_version(
            version_doc_bytes=doc_bytes, version_doc_sig_b64=doc_sig, expected_public_pem=pub,
            target="linux-x86_64", home=layout.decoy_home(), download=_file_download,
            run_self_check=False, post_swap_validate=lambda cur: False,
        )
    assert layout.read_current_version() == "0.1.0"
    assert (layout.version_dir("0.1.0") / "LIVE_MARK").read_text() == "original live 0.1.0"


def test_same_version_promotion_failure_preserves_runtime(tmp_path, monkeypatch, keypair):
    """If promotion itself fails mid-swap (the replacement cannot be moved into place),
    the retained original is put straight back -- a crash never leaves a missing runtime."""
    key, pub = keypair
    monkeypatch.setenv("DECOY_HOME", str(tmp_path / "home"))
    serve = tmp_path / "serve"
    url = _serve_bundle(serve, "0.1.0", key)
    doc_bytes, doc_sig = _doc_for_latest(serve, "0.1.0", url, key)
    installer.install_version(
        version_doc_bytes=doc_bytes, version_doc_sig_b64=doc_sig, expected_public_pem=pub,
        target="linux-x86_64", home=layout.decoy_home(), download=_file_download,
        run_self_check=False, post_swap_validate=lambda cur: True,
    )
    dest = layout.version_dir("0.1.0")
    (dest / "LIVE_MARK").write_text("original live 0.1.0")

    real_replace = os.replace

    def selective_replace(src, dst):
        # Fail only the staged -> dest promotion; allow dest -> backup and the
        # backup -> dest restore (identified by their dot-prefixed temp names).
        if Path(src).name.startswith(".staged.") and Path(dst).name == "0.1.0":
            raise OSError("injected promotion failure")
        return real_replace(src, dst)

    monkeypatch.setattr(installer.os, "replace", selective_replace)
    with pytest.raises(installer.InstallError, match=r"restored|intact"):
        installer.install_version(
            version_doc_bytes=doc_bytes, version_doc_sig_b64=doc_sig, expected_public_pem=pub,
            target="linux-x86_64", home=layout.decoy_home(), download=_file_download,
            run_self_check=False, post_swap_validate=lambda cur: True,
        )
    # The original bits are back in place (reading uses open(), not the patched os.replace).
    assert (layout.version_dir("0.1.0") / "LIVE_MARK").read_text() == "original live 0.1.0"


# ----------------------------------------------------- HIGH 4: Windows gated off matrix
def test_windows_gated_off_advertised_matrix():
    """Windows is removed from the advertised matrix this cycle: it is not a supported
    target and the host does not resolve to one (loud refusal), so no Windows artifact is
    ever advertised (make_version_document iterates SUPPORTED_TARGETS)."""
    assert "windows-x86_64" not in targets.SUPPORTED_TARGETS
    assert targets.detect_target("Windows", "AMD64") is None
    assert set(targets.SUPPORTED_TARGETS) == {"linux-x86_64", "linux-aarch64", "macos-arm64"}


def test_build_bundle_refuses_windows_target(tmp_path, monkeypatch):
    """The assembler refuses to build a target outside the advertised matrix, so a
    Windows bundle cannot be produced to serve."""
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    from packaging_tools import build_bundle

    rc = build_bundle.main([
        "--version", "0.1.0", "--target", "windows-x86_64",
        "--python", str(tmp_path / "py"), "--wheels", str(tmp_path / "wh"),
        "--out", str(tmp_path / "out"),
    ])
    assert rc == 2
    assert not (tmp_path / "out").exists()  # refused before assembling anything


# ------------------------------------------------- LOW 2: pin path isolates the signature
def test_installer_pin_flipped_byte_refuses_on_signature(tmp_path, monkeypatch, keypair):
    """On the PIN path the sidecar checksum is best-effort, so the Ed25519 signature is the
    sole trust anchor. With no sidecar, a flipped byte must refuse specifically on
    SIGNATURE (not checksum) -- isolating the signature branch."""
    key, pub = keypair
    monkeypatch.setenv("DECOY_HOME", str(tmp_path / "home"))
    serve = tmp_path / "serve"
    latest_url = _serve_bundle(serve, "0.2.0", key)
    pin_url = _serve_bundle(serve, "0.1.0", key)
    tar = Path(pin_url[len("file://"):])
    b = tar.read_bytes()
    tar.write_bytes(b[:-1] + bytes([b[-1] ^ 0xFF]))  # flip a byte
    tar.with_name(tar.name + ".sha256").unlink()  # no checksum fallback on the pin path
    doc_bytes, doc_sig = _doc_for_latest(serve, "0.2.0", latest_url, key)

    with pytest.raises(installer.InstallError, match="signature invalid"):
        installer.install_version(
            version_doc_bytes=doc_bytes, version_doc_sig_b64=doc_sig, expected_public_pem=pub,
            target="linux-x86_64", home=layout.decoy_home(), pin_version="0.1.0",
            base_url=f"file://{serve}", download=_file_download, run_self_check=False,
        )


# --------------------------------------- MEDIUM 1 / LOW 1: upgrade network + --force routing
def _call_upgrade(**kwargs):
    """Invoke the `decoy upgrade` command function with explicit args (bypassing Typer)."""
    from decoy.cli import upgrade as upg

    defaults = dict(version=None, check=False, force=False, url=None, json_=False, quiet=True, verbose=False)
    defaults.update(kwargs)
    return upg.upgrade(**defaults)


def test_upgrade_resolves_local_before_network(tmp_path, monkeypatch):
    """`decoy upgrade --version <local>` activates the retained runtime WITHOUT touching
    the version endpoint, so an endpoint outage never blocks a local rollback."""
    from decoy.cli import upgrade as upg

    monkeypatch.setattr(upg, "_managed_home", lambda: tmp_path / "home")
    monkeypatch.setattr(upg.release_key, "pinned_public_pem", lambda: "PUBKEY")
    monkeypatch.setattr(upg.installer, "local_version_present", lambda v, h: True)
    activated = {}

    def fake_activate(version, home, expected_public_pem):
        activated["v"] = version
        return installer.InstallOutcome(version, "linux-x86_64", Path("x"), "0.2.0", False)

    monkeypatch.setattr(upg.installer, "activate_local_version", fake_activate)

    def forbidden(url):
        raise AssertionError("network must not be touched for a local activation")

    monkeypatch.setattr(upg, "_fetch", forbidden)
    with pytest.raises(typer.Exit) as ei:
        _call_upgrade(version="0.1.0")
    assert ei.value.exit_code == 0
    assert activated["v"] == "0.1.0"


def test_upgrade_force_local_reinstalls_not_swap(tmp_path, monkeypatch):
    """`decoy upgrade --version <local> --force` is a repair: it re-downloads and
    re-verifies (install_version) instead of swapping to the retained local bits."""
    from decoy.cli import upgrade as upg

    monkeypatch.setattr(upg, "_managed_home", lambda: tmp_path / "home")
    monkeypatch.setattr(upg.release_key, "pinned_public_pem", lambda: "PUBKEY")
    monkeypatch.setattr(upg.installer, "local_version_present", lambda v, h: True)

    def must_not_activate(*a, **k):
        raise AssertionError("--force must reinstall, not swap to the local runtime")

    monkeypatch.setattr(upg.installer, "activate_local_version", must_not_activate)
    monkeypatch.setattr(upg, "_fetch", lambda url: b"{}")
    monkeypatch.setattr(upg.vd, "verify_document", lambda *a, **k: True)
    monkeypatch.setattr(upg.vd, "parse_document", lambda data: {"latest": "0.1.0"})
    monkeypatch.setattr(upg.vd, "newer_available", lambda cur, doc: False)
    seen = {}

    def fake_install(**k):
        seen["pin"] = k.get("pin_version")
        return installer.InstallOutcome("0.1.0", "linux-x86_64", Path("x"), "0.1.0", False)

    monkeypatch.setattr(upg.installer, "install_version", fake_install)
    with pytest.raises(typer.Exit) as ei:
        _call_upgrade(version="0.1.0", force=True, url="http://x/version.json")
    assert ei.value.exit_code == 0
    assert seen["pin"] == "0.1.0"  # reinstall of the pinned version, not a local swap


# ------------------------------------------------------- MEDIUM 2: no public network bind
def test_smoke_serve_binds_loopback_only():
    """The install smoke must bind its release-serving HTTP listener to loopback, never to
    all interfaces (no public network bind)."""
    src = (REPO_ROOT / "packaging_tools" / "smoke_install.py").read_text(encoding="utf-8")
    assert '("127.0.0.1", 0)' in src  # binds loopback
    assert '("0.0.0.0"' not in src  # never binds all interfaces


# ================================================= round 3 (Codex round-2 findings) =====

# ----- HIGH 1: unsigned code must not shadow the signed runtime (import isolation) -------
def test_managed_launches_pass_import_isolation_flag():
    """Every managed-interpreter invocation -- the shipped bundle launcher AND the install-
    and activation-time verifier/self-checks -- must pass `-I` (isolated mode) alongside
    `-B`, so a hostile CWD or PYTHONPATH cannot shadow the signed runtime with a planted
    `decoy`/`decoy_engine` package. Mechanical guard: an edit that drops `-I` from any of
    these sites is caught here."""
    launcher = (REPO_ROOT / "packaging_tools" / "build_bundle.py").read_text(encoding="utf-8")
    assert '-I -B -m decoy "$@"' in launcher  # the shipped runtime entry point

    inst = (REPO_ROOT / "src" / "decoy" / "distribution" / "installer.py").read_text(encoding="utf-8")
    assert '"-I", "-B", "-m", "decoy.distribution.selfcheck"' in inst  # install + activation self-check

    sh = (REPO_ROOT / "packaging_tools" / "install" / "install.sh").read_text(encoding="utf-8")
    assert "-I -B -m decoy.distribution.verify_extracted" in sh
    assert "-I -B -m decoy.distribution.selfcheck" in sh
    assert "-I -B -m decoy.distribution.layout_point" in sh

    ps = (REPO_ROOT / "packaging_tools" / "install" / "install.ps1").read_text(encoding="utf-8")
    assert "-I -B -m decoy.distribution.verify_extracted" in ps
    assert "-I -B -m decoy.distribution.selfcheck" in ps
    assert "-I -B -m decoy.distribution.layout_point" in ps
    assert "-I -B -m decoy %*" in ps  # the Windows launcher shim


def _plant_hostile_decoy(pkg_parent: Path, marker: Path) -> None:
    """Write a `decoy/__init__.py` under ``pkg_parent`` that records its own execution by
    creating ``marker`` on import -- a stand-in for attacker code that runs if an unsigned
    `decoy` package on the CWD / PYTHONPATH is ever imported in place of the signed one."""
    (pkg_parent / "decoy").mkdir(parents=True, exist_ok=True)
    (pkg_parent / "decoy" / "__init__.py").write_text(
        "import pathlib\n"
        f"pathlib.Path({str(marker)!r}).write_text('executed')\n",
        encoding="utf-8",
    )


_IMPORT_DECOY_PROG = (
    "import sys\n"
    "try:\n"
    "    import decoy\n"
    "    sys.stdout.write(getattr(decoy, '__file__', '') or '')\n"
    "except Exception as exc:\n"
    "    sys.stdout.write('IMPORTERROR:' + type(exc).__name__)\n"
)


def test_import_isolation_blocks_hostile_cwd_and_pythonpath(tmp_path):
    """Functional proof of the `-I` property the launcher/self-checks rely on: a planted
    `decoy` package in the working directory AND one on PYTHONPATH must NOT execute when
    the interpreter runs isolated. The planted code writes a marker on import; under `-I`
    no marker appears (and any real `decoy` that does import resolves from OUTSIDE the
    hostile dirs). Negative controls WITHOUT `-I` show both plants are real, so this guard
    cannot silently rot into a no-op."""
    import subprocess as sp

    hostile_cwd = tmp_path / "downloaded_project"
    cwd_marker = tmp_path / "pwned_from_cwd"
    _plant_hostile_decoy(hostile_cwd, cwd_marker)

    hostile_pp = tmp_path / "evil_pythonpath"
    pp_marker = tmp_path / "pwned_from_pythonpath"
    _plant_hostile_decoy(hostile_pp, pp_marker)

    neutral = tmp_path / "neutral"
    neutral.mkdir()

    def _reset_markers() -> None:
        for m in (cwd_marker, pp_marker):
            if m.exists():
                m.unlink()

    # 1) ISOLATED: both hostile vectors present at once. `-I` must keep both off sys.path.
    _reset_markers()
    env = dict(os.environ, PYTHONPATH=str(hostile_pp), DECOY_PWNED="1")
    iso = sp.run(
        [sys.executable, "-I", "-B", "-c", _IMPORT_DECOY_PROG],
        cwd=str(hostile_cwd), env=env, capture_output=True, text=True,
    )
    assert not cwd_marker.exists(), "hostile CWD `decoy` executed under -I"
    assert not pp_marker.exists(), "hostile PYTHONPATH `decoy` executed under -I"
    # If a real decoy is importable isolated, it must come from neither hostile dir.
    if not iso.stdout.startswith("IMPORTERROR"):
        assert str(hostile_cwd) not in iso.stdout
        assert str(hostile_pp) not in iso.stdout

    # 2) NEGATIVE CONTROL A (no -I, run from the hostile project): the CWD plant executes.
    _reset_markers()
    sp.run(
        [sys.executable, "-B", "-c", _IMPORT_DECOY_PROG],
        cwd=str(hostile_cwd), env=dict(os.environ), capture_output=True, text=True,
    )
    assert cwd_marker.exists(), "the CWD plant is not real; the isolation test is vacuous"

    # 3) NEGATIVE CONTROL B (no -I, neutral CWD, hostile PYTHONPATH): the PYTHONPATH plant executes.
    _reset_markers()
    sp.run(
        [sys.executable, "-B", "-c", _IMPORT_DECOY_PROG],
        cwd=str(neutral), env=dict(os.environ, PYTHONPATH=str(hostile_pp)),
        capture_output=True, text=True,
    )
    assert pp_marker.exists(), "the PYTHONPATH plant is not real; the isolation test is vacuous"


# ----- HIGH 2: the SHELL installer must stage-beside, never destroy-before-promote -------
def test_install_sh_promotion_failure_preserves_active_runtime(tmp_path, keypair):
    """install.sh must not delete the active versions/<version> runtime before the
    replacement is promoted. Inject a promotion failure (the activation step fails) while a
    runtime for that version is already installed and active, and assert the ORIGINAL bits
    survive -- not a missing runtime, and not only the quarantined replacement that the EXIT
    trap would then also remove. Driven over the offline (DECOY_LOCAL_BUNDLE) path."""
    import subprocess as sp

    host_target = targets.detect_target()
    if host_target is None:
        pytest.skip("no supported bundle target for this host")

    key, pub = keypair
    work = tmp_path / "w"
    work.mkdir()

    # A validly-signed replacement bundle whose interpreter PASSES verify/self-check but
    # FAILS the `layout_point` activation step (so promotion happens, then activation fails).
    stage = work / f"decoy-0.1.0-{host_target}"
    stage.mkdir()
    _make_tree(stage)
    dispatch = (
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *layout_point*) exit 7 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n"
    )
    (stage / "python" / "bin" / "python3.12").write_text(dispatch)
    (stage / "python" / "bin" / "python3.12").chmod(0o755)
    (stage / "BUNDLE_INFO.json").write_bytes(
        signing.canonical_bytes(
            {"schema_version": "cli-bundle-info/v1", "version": "0.1.0", "target": host_target}
        )
    )
    man = manifest_mod.compute_manifest(stage, version="0.1.0", target=host_target)
    mb = signing.canonical_bytes(man)
    (stage / manifest_mod.MANIFEST_NAME).write_bytes(mb)
    (stage / manifest_mod.MANIFEST_SIG_NAME).write_text(_sign_b64(key, mb))
    tarball = work / f"decoy-0.1.0-{host_target}.tar.gz"
    _deterministic_targz(stage, tarball)
    tarball.with_name(tarball.name + ".sha256").write_text(
        f"{manifest_mod.sha256_file(tarball)}  {tarball.name}\n"
    )
    tarball.with_name(tarball.name + ".sig").write_text(_sign_b64(key, tarball.read_bytes()))

    pub_pem = work / "pub.pem"
    pub_pem.write_text(pub)

    # Pre-seed an installed + active 0.1.0 runtime (the working bits that must survive).
    home = work / "home"
    versions = home / "versions"
    dest = versions / "0.1.0"
    dest.mkdir(parents=True)
    (dest / "LIVE_MARK").write_text("original live 0.1.0 runtime")
    (home / "current").symlink_to(Path("versions") / "0.1.0")

    install_sh = REPO_ROOT / "packaging_tools" / "install" / "install.sh"
    env = dict(os.environ, DECOY_HOME=str(home), DECOY_BIN_DIR=str(work / "bin"),
               DECOY_RELEASE_PUBKEY_FILE=str(pub_pem), DECOY_LOCAL_BUNDLE=str(tarball))
    r = sp.run(["sh", str(install_sh), "--version", "0.1.0"], env=env, capture_output=True, text=True)

    assert r.returncode != 0, r.stdout + r.stderr  # the injected activation failure refuses
    assert "intact" in r.stderr  # the refusal states the previous runtime was preserved
    # The original working bits survived (restored from the retained backup), not destroyed.
    assert (dest / "LIVE_MARK").read_text() == "original live 0.1.0 runtime"
    # No orphaned promotion scratch dirs are left behind.
    leftovers = [d.name for d in versions.iterdir() if d.name.startswith(".")]
    assert leftovers == [], leftovers


# ----- MEDIUM: `decoy upgrade --check --version <installed>` must be read-only -----------
def test_upgrade_check_version_is_read_only(tmp_path, monkeypatch, keypair):
    """`decoy upgrade --check --version <installed>` must NOT activate the local runtime
    (swap `current`, rewrite the launcher): `--check` reports only. Regression for the
    round-2 local-before-network fast path having run AHEAD of the `--check` guard."""
    from decoy.cli import upgrade as upg

    key, pub = keypair
    monkeypatch.setenv("DECOY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DECOY_BIN_DIR", str(tmp_path / "bin"))
    home = layout.decoy_home()
    serve = tmp_path / "serve"

    # Install 0.1.0 then 0.2.0 so `current` -> 0.2.0 and 0.1.0 is a retained local runtime.
    urls: dict[str, str] = {}
    for ver in ("0.1.0", "0.2.0"):
        urls[ver] = _serve_bundle(serve, ver, key)
        doc_bytes, doc_sig = _doc_for_latest(serve, ver, urls[ver], key)
        installer.install_version(
            version_doc_bytes=doc_bytes, version_doc_sig_b64=doc_sig, expected_public_pem=pub,
            target="linux-x86_64", home=home, download=_file_download,
            run_self_check=False, post_swap_validate=lambda cur: True,
        )
    assert layout.read_current_version(home) == "0.2.0"
    launcher = tmp_path / "bin" / "decoy"
    before_launcher = launcher.read_text()

    # A signed doc whose latest is the installed current version (no newer available).
    doc2, sig2 = _doc_for_latest(serve, "0.2.0", urls["0.2.0"], key)

    def fake_fetch(u: str) -> bytes:
        return sig2.encode("ascii") if u.endswith(".sig") else doc2

    monkeypatch.setattr(upg, "_managed_home", lambda: home)
    monkeypatch.setattr(upg.release_key, "pinned_public_pem", lambda: pub)
    monkeypatch.setattr(upg, "_fetch", fake_fetch)

    # Spy on activation: `--check` must never call it, even for an installed --version.
    real_activate = upg.installer.activate_local_version
    calls: list[str] = []

    def spy_activate(version, *a, **k):
        calls.append(version)
        return real_activate(version, *a, **k)

    monkeypatch.setattr(upg.installer, "activate_local_version", spy_activate)

    with pytest.raises(typer.Exit) as ei:
        _call_upgrade(version="0.1.0", check=True, url="http://host/cli/version.json")
    assert ei.value.exit_code == 0
    assert calls == [], "`--check` must not activate the local runtime"
    assert layout.read_current_version(home) == "0.2.0"  # pointer unchanged
    assert launcher.read_text() == before_launcher  # launcher unchanged
