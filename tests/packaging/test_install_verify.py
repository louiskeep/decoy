"""Installer acceptance: verify-before-extract, and loud refusal on tamper.

This is the headline B-2 acceptance (distribution spec S3): the installer refuses
on a bad checksum or a bad signature, proven with a tampered artifact, and
installs NOTHING on a failed verify. It drives the real shell scripts end to end:
assemble a tiny fake bundle, sign it with a generated test key, install it, then
tamper the bundle and the signature and assert a hard refusal with an empty
install root.

Requires a posix shell, `openssl`, `tar`, and `sha256sum`/`shasum`, and that the
host maps to the `linux-x86_64` target (the CI Linux runner and the devbox do).
The test skips cleanly elsewhere rather than asserting on the wrong target.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGING = REPO_ROOT / "packaging"
INSTALL_SH = PACKAGING / "install" / "install.sh"
SIGN_SH = PACKAGING / "sign" / "sign.sh"
GENKEY_SH = PACKAGING / "sign" / "gen-test-key.sh"

if str(PACKAGING) not in sys.path:
    sys.path.insert(0, str(PACKAGING))

from bundle.assemble import BundleSpec, assemble, read_pins  # noqa: E402

_HOST_IS_LINUX_X86_64 = platform.system() == "Linux" and platform.machine() == "x86_64"
_HAVE_TOOLS = all(shutil.which(t) for t in ("openssl", "tar")) and (
    shutil.which("sha256sum") or shutil.which("shasum")
)

pytestmark = pytest.mark.skipif(
    not (_HOST_IS_LINUX_X86_64 and _HAVE_TOOLS),
    reason="installer acceptance needs a linux-x86_64 host with openssl/tar/sha256sum",
)


def _fake_cpython(tmp_path: Path) -> Path:
    cp = tmp_path / "cpython"
    (cp / "bin").mkdir(parents=True)
    (cp / "bin" / "python3").write_text("#!/bin/sh\n")
    return cp


def _wheel_set(tmp_path: Path) -> list[Path]:
    pins = read_pins()
    engine = pins["DECOY_LAUNCH_ENGINE_VERSION"]
    cli = pins["DECOY_LAUNCH_CLI_VERSION"]
    names = [
        f"decoy_cli-{cli}-py3-none-any.whl",
        f"decoy_engine-{engine}-py3-none-any.whl",
        f"decoy_engine_native-{engine}-cp312-cp312-manylinux_2_28_x86_64.whl",
    ]
    out = []
    for n in names:
        p = tmp_path / n
        p.write_bytes(b"fake wheel")
        out.append(p)
    return out


def _sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


@pytest.fixture
def channel(tmp_path):
    """Assemble + sign a bundle into a local 'download channel' dir, and return
    (channel_dir, version, pubkey_path). The channel layout mirrors the real
    host: artifacts under <version>/."""
    pins = read_pins()
    version = pins["DECOY_LAUNCH_CLI_VERSION"]

    build_root = tmp_path / "build"
    spec = BundleSpec.build(
        target_key="linux-x86_64",
        cpython_src=_fake_cpython(tmp_path),
        wheel_paths=_wheel_set(tmp_path),
        output_root=build_root,
        install_wheels=False,
    )
    plan = assemble(spec)
    # A fake venv interpreter so the launcher path exists post-install (the
    # layout check only needs the file to be present, not runnable here).
    venv_bin = plan.bundle_dir / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").write_text("#!/bin/sh\n")

    channel_dir = tmp_path / "channel"
    version_dir = channel_dir / version
    version_dir.mkdir(parents=True)
    tarball = version_dir / f"decoy-{version}-linux-x86_64.tar.gz"
    with tarfile.open(tarball, "w:gz") as tf:
        for item in sorted(plan.bundle_dir.iterdir()):
            tf.add(item, arcname=item.name)
    (channel_dir / version / "version.json").write_text(
        f'{{"schema_version": 1, "latest": "{version}"}}\n'
    )

    keys = tmp_path / "keys"
    gen = _sh(["sh", str(GENKEY_SH), str(keys)])
    assert gen.returncode == 0, gen.stderr
    priv = keys / "decoy-release-test.key"
    pub = keys / "decoy-release.pub"

    sign = _sh(["sh", str(SIGN_SH), str(version_dir), str(priv)])
    assert sign.returncode == 0, sign.stderr
    assert (version_dir / "SHA256SUMS").exists()
    assert (version_dir / "SHA256SUMS.sig").exists()
    return channel_dir, version, pub


def _install_env(tmp_path, channel_dir, pub, extra=None):
    home = tmp_path / "decoy_home"
    binp = tmp_path / "decoy_bin"
    env = dict(os.environ)
    env.update(
        {
            "DECOY_INSTALL_HOME": str(home),
            "DECOY_INSTALL_BIN": str(binp),
            "DECOY_INSTALL_LOCAL_DIR": str(channel_dir),
            "DECOY_INSTALL_PUBKEY": str(pub),
        }
    )
    if extra:
        env.update(extra)
    return env, home, binp


def test_install_succeeds_and_lays_down_runtime(tmp_path, channel):
    channel_dir, version, pub = channel
    # The installer expects artifacts directly under the local dir, keyed by
    # version subdir (same as the network base URL). Point LOCAL_DIR at the
    # version subdir's parent so the "<version>/<artifact>" paths resolve.
    env, home, binp = _install_env(tmp_path, channel_dir, pub)
    proc = _sh(["sh", str(INSTALL_SH), "--version", version], env=env)
    assert proc.returncode == 0, proc.stderr
    version_dir = home / "versions" / version
    assert (version_dir / "bundle-manifest.json").exists()
    assert (home / "current").is_symlink()
    assert (binp / "decoy").is_symlink()


def test_refuses_tampered_tarball(tmp_path, channel):
    channel_dir, version, pub = channel
    tarball = channel_dir / version / f"decoy-{version}-linux-x86_64.tar.gz"
    with tarball.open("ab") as fh:
        fh.write(b"tampered trailing bytes")
    env, home, binp = _install_env(tmp_path, channel_dir, pub)
    proc = _sh(["sh", str(INSTALL_SH), "--version", version], env=env)
    assert proc.returncode != 0
    assert "CHECKSUM MISMATCH" in proc.stderr
    # Nothing installed.
    assert not (home / "versions" / version).exists()
    assert not (binp / "decoy").exists()


def test_refuses_tampered_signature(tmp_path, channel):
    channel_dir, version, pub = channel
    sig = channel_dir / version / "SHA256SUMS.sig"
    data = bytearray(sig.read_bytes())
    data[-1] ^= 0xFF  # flip the last byte of the signature
    sig.write_bytes(bytes(data))
    env, home, binp = _install_env(tmp_path, channel_dir, pub)
    proc = _sh(["sh", str(INSTALL_SH), "--version", version], env=env)
    assert proc.returncode != 0
    assert "SIGNATURE VERIFICATION FAILED" in proc.stderr
    assert not (home / "versions" / version).exists()
    assert not (binp / "decoy").exists()


def test_refuses_tampered_manifest_entry(tmp_path, channel):
    # Change a checksum in the (signed) manifest: the signature no longer matches
    # the manifest, so this must fail at the signature step, before any extract.
    channel_dir, version, pub = channel
    manifest = channel_dir / version / "SHA256SUMS"
    text = manifest.read_text()
    manifest.write_text(text.replace(text[:4], "dead", 1))
    env, home, _binp = _install_env(tmp_path, channel_dir, pub)
    proc = _sh(["sh", str(INSTALL_SH), "--version", version], env=env)
    assert proc.returncode != 0
    assert "SIGNATURE VERIFICATION FAILED" in proc.stderr
    assert not (home / "versions" / version).exists()


def test_unsupported_target_fails_loudly(tmp_path, channel):
    # Shadow `uname` with a fake that reports an unsupported arch, and assert the
    # installer refuses before doing anything.
    channel_dir, version, pub = channel
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    fake_uname = fakebin / "uname"
    fake_uname.write_text('#!/bin/sh\nif [ "$1" = "-m" ]; then echo riscv64; else echo Linux; fi\n')
    fake_uname.chmod(0o755)
    env, home, _binp = _install_env(
        tmp_path, channel_dir, pub, extra={"PATH": f"{fakebin}:{os.environ['PATH']}"}
    )
    proc = _sh(["sh", str(INSTALL_SH), "--version", version], env=env)
    assert proc.returncode != 0
    assert "unsupported target" in proc.stderr
    assert not (home / "versions").exists()


def test_uninstall_removes_runtime(tmp_path, channel):
    channel_dir, version, pub = channel
    env, home, binp = _install_env(tmp_path, channel_dir, pub)
    assert _sh(["sh", str(INSTALL_SH), "--version", version], env=env).returncode == 0
    assert home.exists()
    proc = _sh(["sh", str(INSTALL_SH), "uninstall"], env=env)
    assert proc.returncode == 0, proc.stderr
    assert not home.exists()
    assert not (binp / "decoy").exists()
