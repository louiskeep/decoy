"""B-2 CLI-LAUNCH §3 acceptance additions (see the plan's acceptance-to-test matrix).

Closes the gaps the gate flagged beyond `test_distribution.py`: yank enforcement at the
installer and the online shell bootstrap, detached-signature schema enforcement on the real
version-document path, refusal ordering for a mismatched bundle, run-time (not only
install-time) native-companion enforcement of the managed runtime, and the placeholder-key
hard refusal of `decoy upgrade`.
"""

from __future__ import annotations

import base64
import hashlib
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tests.unit.test_distribution import (
    REPO_ROOT,
    _file_download,
    _serve_bundle,
    _sign_b64,
)
from typer.testing import CliRunner

from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from decoy.distribution import installer, layout, runtime_guard, selfcheck, signing
from decoy.distribution import version_document as vd

INSTALL_SH = REPO_ROOT / "packaging_tools" / "install" / "install.sh"


@pytest.fixture
def keypair():
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return key, pub


@pytest.fixture(autouse=True)
def _isolate_managed_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("DECOY_HOME", str(tmp_path / "_managed_home"))
    monkeypatch.setenv("DECOY_BIN_DIR", str(tmp_path / "_managed_bin"))


def _signed_doc(key, serve: Path, latest: str, *, yanked=(), mutate=None):
    """A signed version document for ``latest`` (served from ``serve``) with ``yanked``."""
    url = _serve_bundle(serve, latest, key)
    doc = vd.build_document(serial=1, 
        latest=latest,
        min_supported="0.1.0",
        yanked=list(yanked),
        artifacts={"linux-x86_64": {
            "url": url,
            "sha256": hashlib.sha256(_file_download(url)).hexdigest(),
            "sig": url + ".sig",
        }},
    )
    if mutate:
        mutate(doc)
    data = vd.canonical_document_bytes(doc)
    return data, _sign_b64(key, data)


def _install(doc_bytes, doc_sig, pub, serve, **kw):
    return installer.install_version(
        version_doc_bytes=doc_bytes, version_doc_sig_b64=doc_sig, expected_public_pem=pub,
        target="linux-x86_64", home=layout.decoy_home(), base_url=f"file://{serve}",
        download=_file_download, run_self_check=False, **kw,
    )


# ------------------------------------------------------------- yank: installer level
def test_installer_refuses_yanked_latest(tmp_path, keypair):
    key, pub = keypair
    serve = tmp_path / "serve"
    doc, sig = _signed_doc(key, serve, "0.2.0", yanked=["0.2.0"])
    with pytest.raises(installer.InstallError, match="yanked"):
        _install(doc, sig, pub, serve)
    assert not layout.versions_dir().exists() or not any(layout.versions_dir().glob("0.2.0*"))
    assert layout.read_current_version() is None


def test_installer_refuses_yanked_pinned_older_even_though_bits_are_valid(tmp_path, keypair):
    key, pub = keypair
    serve = tmp_path / "serve"
    _serve_bundle(serve, "0.1.0", key)  # a perfectly valid, signed 0.1.0 exists
    doc, sig = _signed_doc(key, serve, "0.2.0", yanked=["0.1.0"])
    with pytest.raises(installer.InstallError, match=r"0\.1\.0 is yanked"):
        _install(doc, sig, pub, serve, pin_version="0.1.0")
    assert layout.read_current_version() is None


def test_installer_installs_unyanked_pin_when_another_version_is_yanked(tmp_path, keypair):
    key, pub = keypair
    serve = tmp_path / "serve"
    _serve_bundle(serve, "0.1.0", key)
    doc, sig = _signed_doc(key, serve, "0.2.0", yanked=["0.0.9"])
    assert _install(doc, sig, pub, serve, pin_version="0.1.0").version == "0.1.0"


# --------------------------------------------- yank + schema: online shell bootstrap
needs_shell_tools = pytest.mark.skipif(
    not (shutil.which("openssl") and shutil.which("curl")), reason="needs openssl + curl"
)


def _run_install_sh(tmp_path: Path, pub: str, version_json: Path, *args: str):
    pub_pem = tmp_path / "pub.pem"
    pub_pem.write_text(pub)
    home = tmp_path / "sh_home"
    env = dict(
        os.environ, DECOY_HOME=str(home), DECOY_BIN_DIR=str(tmp_path / "sh_bin"),
        DECOY_RELEASE_PUBKEY_FILE=str(pub_pem), DECOY_VERSION_URL=f"file://{version_json}",
    )
    env.pop("DECOY_LOCAL_BUNDLE", None)
    r = subprocess.run(["sh", str(INSTALL_SH), *args], env=env, capture_output=True, text=True)
    return r, home


def _publish_doc(tmp_path: Path, key, data: bytes) -> Path:
    path = tmp_path / "version.json"
    path.write_bytes(data)
    Path(str(path) + ".sig").write_text(_sign_b64(key, data))
    return path


@needs_shell_tools
def test_install_sh_online_bootstrap_refuses_yanked_latest(tmp_path, keypair):
    key, pub = keypair
    doc, _ = _signed_doc(key, tmp_path / "serve", "0.2.0", yanked=["0.2.0"])
    r, home = _run_install_sh(tmp_path, pub, _publish_doc(tmp_path, key, doc))
    assert r.returncode != 0
    assert "is yanked" in r.stderr
    assert "downloaded" not in r.stderr and not (home / "versions").exists()


@needs_shell_tools
def test_install_sh_online_bootstrap_refuses_yanked_pin(tmp_path, keypair):
    key, pub = keypair
    serve = tmp_path / "serve"
    _serve_bundle(serve, "0.1.0", key)
    doc, _ = _signed_doc(key, serve, "0.2.0", yanked=["0.1.0"])
    r, home = _run_install_sh(tmp_path, pub, _publish_doc(tmp_path, key, doc), "--version", "0.1.0")
    assert r.returncode != 0 and "version 0.1.0 is yanked" in r.stderr
    assert not (home / "versions").exists() and not (home / "current").exists()


@needs_shell_tools
def test_install_sh_yank_check_is_not_a_substring_match(tmp_path, keypair):
    """A yanked '0.1.01' (or any superstring) must not block '0.1.0'; the refusal that
    follows is the (intentionally unreachable) bundle fetch, not the yank gate."""
    key, pub = keypair
    doc, _ = _signed_doc(key, tmp_path / "serve", "0.2.0", yanked=["0.2.01"])
    r, _ = _run_install_sh(tmp_path, pub, _publish_doc(tmp_path, key, doc))
    assert "yanked" not in r.stderr


@needs_shell_tools
def test_install_sh_rejects_signed_document_of_wrong_schema(tmp_path, keypair):
    key, pub = keypair
    doc, _ = _signed_doc(key, tmp_path / "serve", "0.2.0", mutate=lambda d: d.update(schema_version="other/v9"))
    r, home = _run_install_sh(tmp_path, pub, _publish_doc(tmp_path, key, doc))
    assert r.returncode != 0 and "schema_version" in r.stderr
    assert not (home / "versions").exists()


@needs_shell_tools
def test_install_sh_rejects_unsafe_version_string(tmp_path, keypair):
    key, pub = keypair
    doc, _ = _signed_doc(key, tmp_path / "serve", "0.2.0")
    r, _ = _run_install_sh(tmp_path, pub, _publish_doc(tmp_path, key, doc), "--version", '0.1.0"]*')
    assert r.returncode != 0 and "invalid version string" in r.stderr


# ----------------------------- detached-signature schema enforcement (real install path)
@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(schema_version="cli-version-document/v2"),
        lambda d: d.pop("schema_version"),
    ],
)
def test_signed_document_with_wrong_schema_is_refused_not_crashed(tmp_path, keypair, mutate):
    """A CORRECTLY signed document whose schema is not v1 is a hard InstallError on the
    detached path (the signature proves origin, not shape)."""
    key, pub = keypair
    serve = tmp_path / "serve"
    doc, sig = _signed_doc(key, serve, "0.2.0", mutate=mutate)
    assert vd.verify_document(doc, sig, expected_public_pem=pub)
    with pytest.raises(installer.InstallError, match="version document rejected"):
        _install(doc, sig, pub, serve)
    assert layout.read_current_version() is None


@pytest.mark.parametrize("raw", [b"not json at all", b"[1,2,3]", b'"a string"', b"null"])
def test_signed_non_object_document_is_refused_not_crashed(tmp_path, keypair, raw):
    key, pub = keypair
    with pytest.raises(installer.InstallError, match="version document rejected"):
        _install(raw, _sign_b64(key, raw), pub, tmp_path)


def test_unsigned_or_foreign_signature_never_reaches_schema_parse(tmp_path, keypair):
    _, pub = keypair
    other = _sign_b64(Ed25519PrivateKey.generate(), b"{}")
    for sig in ("", "!!notb64!!", other):
        with pytest.raises(installer.InstallError, match="signature invalid"):
            _install(b'{"schema_version":"cli-version-document/v1"}', sig, pub, tmp_path)


def test_detached_verify_rejects_truncated_and_wrong_algorithm_key(keypair):
    key, pub = keypair
    data = b"doc"
    good = _sign_b64(key, data)
    assert signing.verify_detached(data, good, expected_public_pem=pub)
    raw = base64.b64decode(good)
    assert not signing.verify_detached(data, base64.b64encode(raw[:-1]).decode(), expected_public_pem=pub)
    assert not signing.verify_detached(data, base64.b64encode(raw + b"\0").decode(), expected_public_pem=pub)
    from cryptography.hazmat.primitives.asymmetric import ec

    ec_pub = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    assert not signing.verify_detached(data, good, expected_public_pem=ec_pub)


# ------------------------------------------------------------------- refusal ordering
def _tree_digest(root: Path) -> dict[str, str]:
    out = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if rel == "trust_state.json":  # freshness bookkeeping, not part of any runtime
            continue
        out[rel] = (
            "link:" + os.readlink(p) if p.is_symlink()
            else hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "dir"
        )
    return out


@pytest.mark.parametrize("kind", ["version", "target"])
def test_wrong_identity_bundle_refused_before_selfcheck_and_retained_runtime_untouched(
    tmp_path, monkeypatch, keypair, kind
):
    """A validly signed bundle declaring another version/target is refused BEFORE the new
    bundle's interpreter is executed (self-check) and before any slot is staged; the
    retained runtime (live `current` + its slot) is byte-identical afterwards."""
    key, pub = keypair
    serve = tmp_path / "serve"
    home = layout.decoy_home()
    base_doc, base_sig = _signed_doc(key, serve, "0.1.0")
    _install(base_doc, base_sig, pub, serve)
    before = _tree_digest(home)

    if kind == "version":
        _serve_bundle(serve, "0.3.0", key, declared="0.9.9")
    else:
        _serve_bundle(serve, "0.3.0", key, declared_target="macos-arm64")
    doc, sig = _signed_doc(key, serve, "0.4.0")

    ran = []
    monkeypatch.setattr(installer, "_selfcheck", lambda py: ran.append(py))
    with pytest.raises(installer.InstallError, match=f"declares {kind}"):
        installer.install_version(
            version_doc_bytes=doc, version_doc_sig_b64=sig, expected_public_pem=pub,
            target="linux-x86_64", home=home, pin_version="0.3.0", base_url=f"file://{serve}",
            download=_file_download, run_self_check=True,
        )
    assert ran == [], "the mismatched bundle's interpreter must never be executed"
    assert _tree_digest(home) == before
    assert layout.read_current_version(home) == "0.1.0"


# ------------------------------------- run-time native-companion enforcement (managed)
class _Status:
    def __init__(self, ok, present, reason, abi_actual="decoy-native-abi-3"):
        self.ok, self.present, self.reason = ok, present, reason
        self.version, self.abi_expected, self.abi_actual = "0.1.0", "decoy-native-abi-3", abi_actual


def _fake_probe(monkeypatch, status):
    import types

    monkeypatch.setitem(sys.modules, "decoy_engine", types.SimpleNamespace(native_companion_status=lambda: status))


def _invoke(*args):
    from decoy.__main__ import app

    return CliRunner().invoke(app, ["--no-update-check", *args])


@pytest.mark.parametrize(
    "status",
    [
        _Status(False, False, "absent"),  # companion removed after install
        _Status(False, True, "abi-mismatch", abi_actual="decoy-native-abi-9"),  # swapped after install
    ],
    ids=["removed-after-install", "abi-mismatch-after-install"],
)
def test_managed_runtime_refuses_at_run_time_when_companion_breaks(monkeypatch, tmp_path, status):
    monkeypatch.setattr(layout, "managed_home", lambda: tmp_path)
    _fake_probe(monkeypatch, status)
    res = _invoke("info")
    assert res.exit_code == EXIT_RUNTIME
    assert "native companion check FAILED at run time" in res.output
    assert "decoy upgrade --force" in res.output


def test_managed_runtime_runs_when_companion_is_healthy(monkeypatch, tmp_path):
    monkeypatch.setattr(layout, "managed_home", lambda: tmp_path)
    _fake_probe(monkeypatch, _Status(True, True, "present-ok"))
    assert _invoke("info").exit_code == 0


def test_pip_dev_install_keeps_import_contract_and_is_never_guarded(monkeypatch):
    """No `versions` ancestor => not managed => the engine's optional-accelerator contract
    stands: a missing companion is NOT a refusal."""
    monkeypatch.setattr(layout, "managed_home", lambda: None)
    _fake_probe(monkeypatch, _Status(False, False, "absent"))
    assert runtime_guard.enforce("info") is None
    assert _invoke("info").exit_code == 0


def test_upgrade_stays_runnable_on_a_broken_managed_runtime(monkeypatch, tmp_path):
    """`decoy upgrade` is the repair path, so the guard must not block it. With the
    placeholder key it then hard-refuses itself (EXIT_USAGE) -- distinct from the guard's
    EXIT_RUNTIME, proving the command body was reached."""
    monkeypatch.setattr(layout, "managed_home", lambda: tmp_path)
    monkeypatch.delenv("DECOY_RELEASE_PUBKEY_FILE", raising=False)
    _fake_probe(monkeypatch, _Status(False, False, "absent"))
    assert runtime_guard.enforce("upgrade") is None
    res = _invoke("upgrade", "--check")
    assert res.exit_code == EXIT_USAGE
    assert "no pinned release key" in res.output
    assert "native companion check FAILED" not in res.output


def test_placeholder_key_hard_refuses_upgrade_before_any_network(monkeypatch, tmp_path):
    """The shipped placeholder (`__DECOY_RELEASE_PUBLIC_KEY__`) refuses `decoy upgrade`
    before the version endpoint is touched, even inside a managed home."""
    from decoy.cli import upgrade as upg
    from decoy.distribution import release_key

    assert release_key.PLACEHOLDER_MARKER in release_key._KEY_FILE.read_text(encoding="utf-8")
    monkeypatch.delenv("DECOY_RELEASE_PUBKEY_FILE", raising=False)
    monkeypatch.setattr(upg, "_managed_home", lambda: tmp_path)
    monkeypatch.setattr(upg, "_fetch", lambda url: (_ for _ in ()).throw(AssertionError("network touched")))
    for argv in (["upgrade"], ["upgrade", "--version", "0.1.0"], ["upgrade", "--force"]):
        _fake_probe(monkeypatch, _Status(True, True, "present-ok"))
        res = _invoke(*argv)
        assert res.exit_code == EXIT_USAGE, argv
    assert 'PINNED_PUBKEY=' in INSTALL_SH.read_text() and "__DECOY_RELEASE_PUBLIC_KEY__" in INSTALL_SH.read_text()


def _managed_python(tmp_path: Path) -> Path:
    """A real interpreter laid out as ``<home>/versions/0.0.1/python`` so `sys.prefix` makes
    it a managed runtime, wired (via .pth, which survives ``-I``) to this checkout's decoy +
    engine and the test environment's dependencies."""
    import decoy_engine

    import decoy

    prefix = tmp_path / "home" / "versions" / "0.0.1" / "python"
    venv.EnvBuilder(with_pip=False, symlinks=True).create(prefix)
    (prefix.parent / "manifest.json").write_text("{}", encoding="utf-8")
    layout.atomic_point_current_at("0.0.1", tmp_path / "home")
    site = next(prefix.glob("lib/python*/site-packages"))
    paths = {
        str(Path(decoy.__file__).resolve().parents[1]),
        str(Path(decoy_engine.__file__).resolve().parents[1]),
        *(p for p in sys.path if p.endswith("site-packages")),
    }
    (site / "paths.pth").write_text("\n".join(sorted(paths)) + "\n", encoding="utf-8")
    return prefix / "bin" / "python"


def _run_managed(py: Path, *args: str):
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env["DECOY_RELEASE_PUBKEY_FILE"] = os.devnull
    return subprocess.run(
        [str(py), "-I", "-B", "-m", "decoy", "--no-update-check", *args],
        capture_output=True, text=True, env=env, cwd=py.parents[3],
    )


def test_real_managed_interpreter_refuses_absent_then_abi_mismatched_companion(tmp_path):
    """Behavioral, no mocks: a real interpreter in a managed layout runs the real engine
    probe. Companion absent -> refused; a stub companion reporting the wrong ABI (the real
    probe's `abi-mismatch`) -> refused; `--version` and `upgrade` stay reachable."""
    if importlib_find("decoy_engine_native"):
        pytest.skip("a real native companion is installed in this environment")
    py = _managed_python(tmp_path)

    absent = _run_managed(py, "info")
    assert absent.returncode == EXIT_RUNTIME, absent.stdout + absent.stderr
    assert "native companion check FAILED at run time" in absent.stderr
    assert "absent" in absent.stderr

    site = next(py.parents[1].glob("lib/python*/site-packages"))
    stub = site / "decoy_engine_native"
    stub.mkdir()
    (stub / "__init__.py").write_text("", encoding="utf-8")
    (stub / "_kernel.py").write_text("def abi_version():\n    return 'decoy-native-abi-0'\n", encoding="utf-8")
    mismatch = _run_managed(py, "info")
    assert mismatch.returncode == EXIT_RUNTIME, mismatch.stdout + mismatch.stderr
    assert "abi-mismatch" in mismatch.stderr

    assert _run_managed(py, "--version").returncode == 0
    up = _run_managed(py, "upgrade", "--check")
    assert up.returncode != EXIT_RUNTIME or "native companion check FAILED" not in up.stderr


def importlib_find(name: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def test_selfcheck_result_shape_is_what_the_guard_consumes():
    assert runtime_guard.refusal_message(selfcheck.SelfCheckResult(True, "present-ok", "x")) is None
    msg = runtime_guard.refusal_message(selfcheck.SelfCheckResult(False, "native-unavailable", "boom"))
    assert msg and "boom" in msg


def _enable_interactive_update_check(monkeypatch, tmp_path):
    """Make the startup notice WOULD-fire: interactive, no opt-out, no cache, and a trap on
    every network entry point so any probe fails the test loudly."""
    from decoy import _update_check

    monkeypatch.delenv("DECOY_NO_UPDATE_CHECK", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("DECOY_HOME", str(tmp_path / "_cache_home"))
    monkeypatch.setattr(_update_check, "_interactive", lambda: True)
    touched: list[str] = []

    def _trap(url, *a, **k):
        touched.append(url)
        raise AssertionError(f"network touched: {url}")

    monkeypatch.setattr(_update_check, "_fetch_latest", _trap)
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", _trap)
    return touched


def _invoke_with_update_check(*args):
    from typer.testing import CliRunner

    from decoy.__main__ import app

    return CliRunner().invoke(app, list(args))


def test_placeholder_key_refuses_through_root_callback_with_update_check_enabled(monkeypatch, tmp_path):
    from decoy.cli import upgrade as upg

    touched = _enable_interactive_update_check(monkeypatch, tmp_path)
    monkeypatch.delenv("DECOY_RELEASE_PUBKEY_FILE", raising=False)
    monkeypatch.setattr(upg, "_managed_home", lambda: tmp_path)
    monkeypatch.setattr(upg, "_fetch", lambda url: touched.append(url) or (_ for _ in ()).throw(AssertionError(url)))
    _fake_probe(monkeypatch, _Status(True, True, "present-ok"))
    res = _invoke_with_update_check("upgrade")
    assert res.exit_code == EXIT_USAGE
    assert "no pinned release key" in res.output
    assert touched == []


def test_local_rollback_through_root_callback_touches_no_network_first(monkeypatch, tmp_path):
    from decoy.cli import upgrade as upg
    from decoy.distribution import installer

    touched = _enable_interactive_update_check(monkeypatch, tmp_path)
    order: list[str] = []
    monkeypatch.setenv("DECOY_RELEASE_PUBKEY_FILE", str(tmp_path / "k.pem"))
    (tmp_path / "k.pem").write_text("pem", encoding="utf-8")
    monkeypatch.setattr(upg, "_managed_home", lambda: tmp_path)
    monkeypatch.setattr(upg, "_fetch", lambda url: touched.append(url) or (_ for _ in ()).throw(AssertionError(url)))
    monkeypatch.setattr(installer, "local_version_present", lambda v, h: True)
    out = installer.InstallOutcome(
        version="0.1.0", target="linux-x86_64", version_dir=tmp_path, previous_version="0.2.0",
        rolled_back=False, rollback_version=None,
    )
    monkeypatch.setattr(installer, "activate_local_version", lambda *a, **k: order.append("LOCAL_ACTIVATION") or out)
    _fake_probe(monkeypatch, _Status(True, True, "present-ok"))
    res = _invoke_with_update_check("upgrade", "--version", "0.1.0")
    assert res.exit_code == 0, res.output
    assert order == ["LOCAL_ACTIVATION"] and touched == []


def test_startup_notice_suppressed_when_pinned_key_is_placeholder(monkeypatch, tmp_path):
    touched = _enable_interactive_update_check(monkeypatch, tmp_path)
    monkeypatch.delenv("DECOY_RELEASE_PUBKEY_FILE", raising=False)
    monkeypatch.setattr(layout, "managed_home", lambda: None)
    assert _invoke_with_update_check("info").exit_code == 0
    assert touched == []
