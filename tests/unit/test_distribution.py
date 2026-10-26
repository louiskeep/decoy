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
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from decoy.distribution import (
    installer,
    layout,
    manifest as manifest_mod,
    release_key,
    signing,
    targets,
    verify_extracted,
    version_document as vd,
)


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


def test_manifest_detects_unexpected_and_ignores_pycache(tmp_path):
    root = tmp_path / "b"
    root.mkdir()
    _make_tree(root)
    man = manifest_mod.compute_manifest(root, version="0.1.0", target="t")
    # regenerable bytecode: added after signing, must NOT be flagged
    pc = root / "python" / "lib" / "__pycache__"
    pc.mkdir(parents=True)
    (pc / "mod.cpython-312.pyc").write_bytes(b"bytecode")
    assert manifest_mod.verify_manifest(man, root) == []
    # a real unexpected file IS flagged
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
        ("Windows", "AMD64", "windows-x86_64"),
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
    doc_bytes, doc_sig, download, tar_bytes, sha = _synthetic_release(tmp_path, key, pub)
    # Corrupt the served tarball so its signature no longer matches.
    bad = tmp_path / "serve" / "decoy-0.1.0-linux-x86_64.tar.gz"
    bad.write_bytes(tar_bytes[:-1] + bytes([tar_bytes[-1] ^ 0xFF]))

    with pytest.raises(installer.InstallError, match="signature invalid|checksum mismatch"):
        installer.install_version(
            version_doc_bytes=doc_bytes, version_doc_sig_b64=doc_sig,
            expected_public_pem=pub, target="linux-x86_64",
            home=layout.decoy_home(), download=download, run_self_check=False,
        )


def test_installer_rejects_checksum_mismatch(tmp_path, monkeypatch, keypair):
    key, pub = keypair
    monkeypatch.setenv("DECOY_HOME", str(tmp_path / "home"))
    # Hand-build a document whose declared sha256 is wrong but still signed.
    serve = tmp_path / "serve"; serve.mkdir()
    stage = tmp_path / "decoy-0.1.0-linux-x86_64"; stage.mkdir()
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
