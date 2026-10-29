"""r7 supply-chain hardening: document freshness / anti-rollback, archive extraction, and the
release trust anchor. Each test fails on the pre-r7 code."""

from __future__ import annotations

import datetime as dt
import io
import tarfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tests.unit.test_distribution_acceptance import (
    _install,
    _publish_doc,
    _run_install_sh,
    _signed_doc,
    needs_shell_tools,
)

from decoy.distribution import installer, layout, release_key
from decoy.distribution import version_document as vd

_FUTURE = "2999-01-01T00:00:00Z"
_PAST = "2001-01-01T00:00:00Z"


@pytest.fixture
def keypair():
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return key, pub


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("DECOY_HOME", str(tmp_path / "_managed_home"))
    monkeypatch.setenv("DECOY_BIN_DIR", str(tmp_path / "_managed_bin"))


_n = iter(range(10_000))


def _doc(key, serve, latest="0.2.0", **fields):
    # _signed_doc stages a bundle under ``serve``; each document gets its own dir.
    return _signed_doc(key, serve / f"d{next(_n)}", latest, mutate=lambda d: d.update(fields))


# ------------------------------------------------------------- freshness: installer
def test_expired_document_is_refused(tmp_path, keypair):
    key, pub = keypair
    serve = tmp_path / "serve"
    doc, sig = _doc(key, serve, serial=5, expires=_PAST)
    with pytest.raises(installer.InstallError, match="expired"):
        _install(doc, sig, pub, serve)
    assert layout.read_current_version() is None


def test_document_without_serial_or_expires_is_rejected(tmp_path, keypair):
    key, pub = keypair
    serve = tmp_path / "serve"
    for field in ("serial", "expires"):
        doc, sig = _signed_doc(key, serve / field, "0.2.0", mutate=lambda d, f=field: d.pop(f))
        with pytest.raises(installer.InstallError, match=field):
            _install(doc, sig, pub, serve)


def test_lower_serial_signed_document_is_refused_after_a_newer_one(tmp_path, keypair):
    key, pub = keypair
    serve = tmp_path / "serve"
    new, new_sig = _doc(key, serve, "0.2.0", serial=10, expires=_FUTURE)
    _install(new, new_sig, pub, serve)
    stale, stale_sig = _doc(key, serve, "0.2.0", serial=9, expires=_FUTURE)
    with pytest.raises(installer.InstallError, match="rollback"):
        _install(stale, stale_sig, pub, serve, pin_version="0.2.0")
    # an equal serial (idempotent re-run / repair) is still accepted
    _install(new, new_sig, pub, serve)


def test_recorded_serial_survives_a_refused_lower_document(tmp_path, keypair):
    key, pub = keypair
    serve = tmp_path / "serve"
    new, new_sig = _doc(key, serve, "0.2.0", serial=10, expires=_FUTURE)
    installer.check_document_freshness(vd.parse_document(new), layout.decoy_home())
    with pytest.raises(installer.InstallError):
        installer.check_document_freshness(
            vd.parse_document(_doc(key, serve, "0.2.0", serial=3, expires=_FUTURE)[0]), layout.decoy_home()
        )
    with pytest.raises(installer.InstallError):
        installer.check_document_freshness(
            vd.parse_document(_doc(key, serve, "0.2.0", serial=9, expires=_FUTURE)[0]), layout.decoy_home()
        )


def test_pin_below_signed_min_supported_is_refused(tmp_path, keypair):
    key, pub = keypair
    serve = tmp_path / "serve"
    doc, sig = _doc(key, serve, "0.3.0", min_supported="0.2.0", serial=2, expires=_FUTURE)
    with pytest.raises(installer.InstallError, match="min_supported"):
        _install(doc, sig, pub, serve, pin_version="0.1.0")


def test_build_document_defaults_expiry_in_the_future():
    doc = vd.build_document(latest="0.1.0", min_supported="0.1.0", artifacts={}, serial=1)
    vd.check_fresh(doc)
    with pytest.raises(ValueError, match="expired"):
        vd.check_fresh(doc, now=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=365))


# ------------------------------------------------------------- freshness: install.sh
@needs_shell_tools
def test_install_sh_refuses_expired_document(tmp_path, keypair):
    key, pub = keypair
    doc, _ = _doc(key, tmp_path / "serve", serial=5, expires=_PAST)
    r, home = _run_install_sh(tmp_path, pub, _publish_doc(tmp_path, key, doc))
    assert r.returncode != 0 and "expired" in r.stderr
    assert not (home / "versions").exists()


@needs_shell_tools
def test_install_sh_refuses_lower_serial_than_recorded(tmp_path, keypair):
    key, pub = keypair
    doc, _ = _doc(key, tmp_path / "serve", serial=4, expires=_FUTURE)
    # first run records serial 4 (it then fails to download: no bundle served -- fine)
    _, home = _run_install_sh(tmp_path, pub, _publish_doc(tmp_path, key, doc))
    assert '"serial":4' in (home / "trust_state.json").read_text()
    stale, _ = _doc(key, tmp_path / "serve", serial=3, expires=_FUTURE)
    r, _ = _run_install_sh(tmp_path, pub, _publish_doc(tmp_path, key, stale))
    assert r.returncode != 0 and "rollback" in r.stderr


@needs_shell_tools
def test_install_sh_refuses_document_missing_serial(tmp_path, keypair):
    key, pub = keypair
    doc, _ = _signed_doc(key, tmp_path / "serve", "0.2.0", mutate=lambda d: d.pop("serial"))
    r, _ = _run_install_sh(tmp_path, pub, _publish_doc(tmp_path, key, doc))
    assert r.returncode != 0 and "serial" in r.stderr


# ------------------------------------------------------------- archive extraction
def _tar(members) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz") as tf:
        for name, kind, extra in members:
            ti = tarfile.TarInfo(name)
            if kind == "dir":
                ti.type = tarfile.DIRTYPE
                tf.addfile(ti)
            elif kind == "file":
                ti.size = len(extra)
                tf.addfile(ti, io.BytesIO(extra))
            elif kind == "sym":
                ti.type, ti.linkname = tarfile.SYMTYPE, extra
                tf.addfile(ti)
            elif kind == "hard":
                ti.type, ti.linkname = tarfile.LNKTYPE, extra
                tf.addfile(ti)
    return raw.getvalue()


@pytest.mark.parametrize(
    "linkname", ["../outside", "/etc/passwd", "b/../../outside"]
)
def test_hardlink_with_escaping_name_is_rejected(tmp_path, linkname):
    data = _tar([
        ("b", "dir", None),
        ("b/ok", "file", b"x"),
        ("b/h", "hard", linkname),
    ])
    with pytest.raises(installer.InstallError, match="hardlink"):
        installer._extract_bundle(data, tmp_path / "out")
    assert not (tmp_path / "outside").exists()


def test_member_written_through_an_earlier_symlink_is_rejected(tmp_path):
    data = _tar([("b", "dir", None), ("b/lnk", "sym", "sub"), ("b/sub", "dir", None), ("b/lnk/f", "file", b"x")])
    with pytest.raises(installer.InstallError, match="through a symlink"):
        installer._extract_bundle(data, tmp_path / "out")


def test_internal_hardlink_and_symlink_still_extract(tmp_path):
    data = _tar([
        ("b", "dir", None), ("b/real", "file", b"x"), ("b/h", "hard", "b/real"), ("b/s", "sym", "real"),
    ])
    root = installer._extract_bundle(data, tmp_path / "out")
    assert (root / "h").read_bytes() == b"x"


def test_extraction_refuses_when_data_filter_is_unavailable(tmp_path, monkeypatch):
    data = _tar([("b", "dir", None), ("b/f", "file", b"x")])
    monkeypatch.delattr(tarfile, "data_filter", raising=False)
    with pytest.raises(installer.InstallError, match="unfiltered"):
        installer._extract_bundle(data, tmp_path / "out")
    assert not (tmp_path / "out" / "b" / "f").exists()


def test_extraction_refuses_when_extractall_rejects_filter_kwarg(tmp_path, monkeypatch):
    data = _tar([("b", "dir", None), ("b/f", "file", b"x")])
    calls = []

    def old_extractall(self, path=".", members=None, *, numeric_owner=False):
        calls.append(path)

    monkeypatch.setattr(tarfile.TarFile, "extractall", old_extractall)
    with pytest.raises(installer.InstallError, match="unfiltered"):
        installer._extract_bundle(data, tmp_path / "out")
    assert calls == []


# ------------------------------------------------------------- trust anchor override
def _write_key(tmp_path, pub) -> Path:
    p = tmp_path / "k.pem"
    p.write_text(pub)
    return p


def test_override_warns_loudly_on_a_placeholder_dev_build(tmp_path, monkeypatch, keypair, capsys):
    monkeypatch.setenv("DECOY_RELEASE_PUBKEY_FILE", str(_write_key(tmp_path, keypair[1])))
    assert release_key.pinned_public_pem() == keypair[1]
    assert "WARNING" in capsys.readouterr().err


def test_override_is_ignored_when_the_build_pins_a_real_key(tmp_path, monkeypatch, keypair, capsys):
    pinned = tmp_path / "pinned.pem"
    pinned.write_text(Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode())
    monkeypatch.setattr(release_key, "_KEY_FILE", pinned)
    monkeypatch.setenv("DECOY_RELEASE_PUBKEY_FILE", str(_write_key(tmp_path, keypair[1])))
    assert release_key.pinned_public_pem() == pinned.read_text()
    assert "IGNORED" in capsys.readouterr().err


@needs_shell_tools
def test_install_sh_ignores_override_when_key_is_pinned(tmp_path, keypair):
    """A release build has the real key injected; an attacker-supplied key via the env must
    not make a document signed by the attacker verify."""
    from tests.unit.test_distribution import REPO_ROOT

    real_key, real_pub = Ed25519PrivateKey.generate(), None
    real_pub = real_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    body = "".join(real_pub.splitlines()[1:-1])
    script = (REPO_ROOT / "packaging_tools/install/install.sh").read_text()
    injected = script.replace("__DECOY_RELEASE_PUBLIC_KEY__", body)
    sh = tmp_path / "install_release.sh"
    sh.write_text(injected)
    attacker, attacker_pub = keypair
    doc, _ = _doc(attacker, tmp_path / "serve", serial=5, expires=_FUTURE)
    import os
    import subprocess

    pk = _write_key(tmp_path, attacker_pub)
    env = dict(os.environ, DECOY_HOME=str(tmp_path / "h"), DECOY_BIN_DIR=str(tmp_path / "b"),
               DECOY_RELEASE_PUBKEY_FILE=str(pk),
               DECOY_VERSION_URL=f"file://{_publish_doc(tmp_path, attacker, doc)}")
    r = subprocess.run(["sh", str(sh)], env=env, capture_output=True, text=True)
    assert r.returncode != 0
    assert "IGNORED" in r.stderr and "signature INVALID" in r.stderr
