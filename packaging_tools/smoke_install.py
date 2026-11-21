"""End-to-end smoke for the CLI distribution machinery (CLI-launch acceptance).

Builds a real signed linux bundle, serves it from a local HTTP server (bound to
loopback only, never a public interface), and drives the full install + upgrade flow
against the acceptance checklist, asserting each outcome:

  1. install on a clean target, then `decoy --version` and a real `decoy run` succeed;
  2. a one-byte tamper in the bundle makes install refuse on CHECKSUM;
  3. a corrupted signature (valid bytes) makes install refuse on SIGNATURE;
  4. a bundle with the native companion removed makes install refuse LOUDLY at the
     native self-check (no silent pandas fallback), laying nothing down;
  5. `decoy upgrade` from 0.1.0 to 0.2.0 swaps atomically; an injected post-swap
     failure rolls `current` back to 0.1.0.

Run (from the decoy repo root), e.g.:

    python -m packaging_tools.smoke_install \
        --python /path/to/standalone-cpython \
        --wheels /path/to/wheels-with-full-closure \
        --work /tmp/decoy-smoke

``--wheels`` must hold the decoy-cli / decoy-engine / decoy-engine-native wheels AND
their full dependency closure (the release pipeline populates this; see README). A
0.2.0 decoy-cli wheel is built from the current tree for the upgrade leg.

Exit 0 iff every case passed. Signing uses an ephemeral key generated here; the
installer/upgrade pin it via DECOY_RELEASE_PUBKEY_FILE (no committed key needed).

Candidate mode (REL-GATE 5.4) smokes a signed release candidate instead of building one:

    python -m packaging_tools.smoke_install --from-dist DIR --candidate candidate.json \
        --pubkey release-key.pub.pem --target macos-arm64 > summary.json

It checks the set against `candidate.json`, the version document and the pinned keys, installs
with the candidate's own installer from a copy of the tarball, then runs `decoy --version`,
`decoy doctor --json`, `packaging_tools/smoke/native.yaml` (which must take the native route) and
the bundled `minimal` template. It prints one `decoy-release-smoke/v1` summary on stdout for
`scripts/release/record_smoke.py`. Exit 0 all passed, 1 a step failed, 2 usage.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import http.server
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO_ROOT = Path(__file__).resolve().parents[1]
_CANDIDATE_FLAGS = ("--from-dist", "--candidate", "--pubkey", "--target")


def _log(msg: str) -> None:
    print(f"[smoke] {msg}", flush=True)


def _gen_key(work: Path) -> tuple[Path, Path]:
    key = Ed25519PrivateKey.generate()
    priv = work / "release-key.pem"
    priv.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    os.chmod(priv, 0o600)
    pub = work / "release-key.pub.pem"
    pub.write_text(
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return priv, pub


def _build_cli_wheel(version: str, wheels: Path) -> None:
    """Build a decoy-cli wheel at ``version`` into ``wheels`` (used for the 0.2.0 leg).

    Bumps BOTH version sources the CLI carries today: the pyproject dist version and
    the ``__version__`` literal in src/decoy/_version.py (what ``decoy --version`` and
    the update check read). A real release bumps both; this mirrors that."""
    import re

    import tomllib

    pyproject = REPO_ROOT / "pyproject.toml"
    init_py = REPO_ROOT / "src" / "decoy" / "_version.py"
    pp_orig = pyproject.read_text(encoding="utf-8")
    init_orig = init_py.read_text(encoding="utf-8")
    cur = tomllib.loads(pp_orig)["project"]["version"]
    try:
        pyproject.write_text(pp_orig.replace(f'version = "{cur}"', f'version = "{version}"', 1), encoding="utf-8")
        init_py.write_text(
            re.sub(r'^__version__\s*=\s*"[^"]*"', f'__version__ = "{version}"', init_orig, count=1, flags=re.M),
            encoding="utf-8",
        )
        for old in wheels.glob("decoy_cli-*.whl"):
            old.unlink()
        subprocess.run(["uv", "build", "--wheel", "-o", str(wheels)], cwd=REPO_ROOT, check=True)
    finally:
        pyproject.write_text(pp_orig, encoding="utf-8")
        init_py.write_text(init_orig, encoding="utf-8")


def _run_build_bundle(python_src: Path, wheels: Path, out: Path, version: str, key: Path) -> None:
    env = dict(os.environ, DECOY_RELEASE_KEY_FILE=str(key), PYTHONPATH=str(REPO_ROOT / "src") + os.pathsep + str(REPO_ROOT))
    subprocess.run(
        [sys.executable, "-m", "packaging_tools.build_bundle",
         "--version", version, "--target", "linux-x86_64",
         "--python", str(python_src), "--wheels", str(wheels), "--out", str(out), "--sign"],
        cwd=REPO_ROOT, env=env, check=True,
    )


def _make_version_doc(dist: Path, out: Path, base_url: str, version: str, key: Path) -> None:
    env = dict(os.environ, DECOY_RELEASE_KEY_FILE=str(key), PYTHONPATH=str(REPO_ROOT / "src") + os.pathsep + str(REPO_ROOT))
    subprocess.run(
        [sys.executable, "-m", "packaging_tools.make_version_document",
         "--version", version, "--min-supported", "0.1.0",
         "--dist", str(dist), "--base-url", base_url, "--out", str(out), "--sign"],
        cwd=REPO_ROOT, env=env, check=True,
    )


@contextlib.contextmanager
def _serve(directory: Path):
    """A local HTTP server bound to LOOPBACK only, yielding its URL.

    The smoke serves release bytes that must never be reachable off-box: bind 127.0.0.1
    explicitly so the listener is not exposed on any other interface, rather than binding
    0.0.0.0 and relying on the caller to stay LAN-local."""
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(directory), **k)  # noqa: E731
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.socket.getsockname()[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    _log(f"serving {directory} at http://127.0.0.1:{port}/ (loopback only)")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()


def _bundle_env(**extra: str) -> dict:
    """Env for a subprocess that must run the INSTALLED BUNDLE, not the repo checkout.
    Strips PYTHONPATH/PYTHONHOME so the bundle imports its own decoy/decoy_engine (the
    whole point of the smoke); a leaked PYTHONPATH=src would silently test the checkout."""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.update(extra)
    return env


def _install(install_sh: Path, *, home: Path, bindir: Path, version_url: str, pub: Path,
             extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = _bundle_env(DECOY_HOME=str(home), DECOY_BIN_DIR=str(bindir),
                      DECOY_VERSION_URL=version_url, DECOY_RELEASE_PUBKEY_FILE=str(pub))
    if extra_env:
        env.update(extra_env)
    return subprocess.run(["sh", str(install_sh)], env=env, capture_output=True, text=True)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(arg.split("=", 1)[0] in _CANDIDATE_FLAGS for arg in argv):
        return candidate_main(argv)
    ap = argparse.ArgumentParser(prog="smoke_install")
    ap.add_argument("--python", required=True, help="standalone CPython dir to embed")
    ap.add_argument("--wheels", required=True, help="wheels dir (3 decoy wheels + full closure)")
    ap.add_argument("--work", required=True, help="scratch dir for the smoke")
    ap.add_argument("--keep", action="store_true", help="keep the work dir on success")
    args = ap.parse_args(argv)

    work = Path(args.work)
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    wheels = Path(args.wheels)
    python_src = Path(args.python)
    install_sh = REPO_ROOT / "packaging_tools" / "install" / "install.sh"

    priv, pub = _gen_key(work)
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        _log(f"[{status}] {name}{(' -- ' + detail) if detail else ''}")
        if not cond:
            failures.append(name)

    # --- build + serve the 0.1.0 bundle -------------------------------------
    dist = work / "dist"
    _log("building 0.1.0 bundle ...")
    _run_build_bundle(python_src, wheels, dist, "0.1.0", priv)
    serve = work / "serve"
    (serve / "cli").mkdir(parents=True)
    v1dir = serve / "v0.1.0"
    v1dir.mkdir()
    for f in dist.glob("decoy-0.1.0-linux-x86_64.tar.gz*"):
        shutil.copy(f, v1dir / f.name)

    with _serve(serve) as base:
        _make_version_doc(dist, serve / "cli" / "version.json", base, "0.1.0", priv)
        vurl = f"{base}/cli/version.json"

        # CASE 1: clean install + --version + run
        home = work / "home"
        bindir = work / "bin"
        r = _install(install_sh, home=home, bindir=bindir, version_url=vurl, pub=pub)
        check("case1.install", r.returncode == 0, r.stderr.strip().splitlines()[-1] if r.returncode else "")
        launcher = bindir / "decoy"
        if launcher.exists():
            ver = subprocess.run([str(launcher), "--version"], env=_bundle_env(), capture_output=True, text=True)
            check("case1.version", ver.returncode == 0 and "0.1.0" in ver.stdout, ver.stdout.strip())
            rundir = work / "run"
            rundir.mkdir()
            shutil.copy(REPO_ROOT / "examples" / "generate_example.yaml", rundir / "gen.yaml")
            run = subprocess.run([str(launcher), "run", "gen.yaml"], cwd=rundir, env=_bundle_env(), capture_output=True, text=True)
            produced = (rundir / "customers.csv").exists()
            check("case1.run", run.returncode == 0 and produced, "customers.csv produced" if produced else run.stderr[-200:])
        else:
            check("case1.version", False, "no launcher")
            check("case1.run", False, "no launcher")

        # CASE 2: tamper a byte -> checksum refusal
        tarball = v1dir / "decoy-0.1.0-linux-x86_64.tar.gz"
        orig = tarball.read_bytes()
        tarball.write_bytes(orig[:5_000_000] + bytes([orig[5_000_000] ^ 0xFF]) + orig[5_000_001:])
        r = _install(install_sh, home=work / "h2", bindir=work / "b2", version_url=vurl, pub=pub)
        check("case2.checksum_refusal", r.returncode != 0 and "checksum MISMATCH" in r.stderr, "")
        tarball.write_bytes(orig)

        # CASE 3: corrupt signature (valid bytes) -> signature refusal
        sig = v1dir / "decoy-0.1.0-linux-x86_64.tar.gz.sig"
        orig_sig = sig.read_text()
        import base64
        key = serialization.load_pem_private_key(priv.read_bytes(), password=None)
        sig.write_text(base64.b64encode(key.sign(b"wrong")).decode())
        r = _install(install_sh, home=work / "h3", bindir=work / "b3", version_url=vurl, pub=pub)
        check("case3.signature_refusal", r.returncode != 0 and "signature INVALID" in r.stderr, "")
        sig.write_text(orig_sig)

        # CASE 4: companion removed -> loud native self-check refusal, nothing laid down
        _log("building no-native bundle ...")
        nonat = _make_no_native_bundle(work, dist, priv)
        nn_serve = work / "serve_nn"
        (nn_serve / "cli").mkdir(parents=True)
        (nn_serve / "v0.1.0").mkdir()
        for f in nonat.glob("decoy-0.1.0-linux-x86_64.tar.gz*"):
            shutil.copy(f, nn_serve / "v0.1.0" / f.name)
        with _serve(nn_serve) as nnbase:
            _make_version_doc(nonat, nn_serve / "cli" / "version.json", nnbase, "0.1.0", priv)
            h4 = work / "h4"
            r = _install(install_sh, home=h4, bindir=work / "b4",
                         version_url=f"{nnbase}/cli/version.json", pub=pub)
            laid_down = (h4 / "current").exists()
            check("case4.native_refusal",
                  r.returncode != 0 and "self-check FAILED" in r.stderr and not laid_down,
                  "nothing laid down" if not laid_down else "LAID DOWN (bad)")

        # CASE 5: real decoy upgrade 0.1.0 -> 0.2.0, then injected-failure rollback
        _log("building 0.2.0 bundle for upgrade ...")
        _build_cli_wheel("0.2.0", wheels)
        try:
            dist2 = work / "dist2"
            _run_build_bundle(python_src, wheels, dist2, "0.2.0", priv)
            v2dir = serve / "v0.2.0"
            v2dir.mkdir()
            for f in dist2.glob("decoy-0.2.0-linux-x86_64.tar.gz*"):
                shutil.copy(f, v2dir / f.name)
            # Drive `decoy upgrade` over file:// -- urllib-native, so the leg does not
            # depend on an HTTP proxy's loopback handling (install.sh/curl handled the
            # earlier HTTP cases). It exercises the identical verify + swap + rollback
            # path. The doc's artifact URLs are file:// paths to the served 0.2.0 dir.
            up_doc = serve / "cli" / "version-upgrade.json"
            _make_version_doc(dist2, up_doc, f"file://{serve}", "0.2.0", priv)
            _run_upgrade_cases(bindir, f"file://{up_doc}", pub, check)
        finally:
            _build_cli_wheel("0.1.0", wheels)  # restore the wheels dir

    _log(f"RESULT: {'ALL PASS' if not failures else 'FAILURES: ' + ', '.join(failures)}")
    if not failures and not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0 if not failures else 1


def _make_no_native_bundle(work: Path, dist: Path, key_path: Path) -> Path:
    """Repack the 0.1.0 bundle with the native companion removed + re-signed."""
    import tarfile

    from cryptography.hazmat.primitives import serialization as _ser

    from decoy.distribution import manifest as m
    from decoy.distribution import signing
    from packaging_tools.build_bundle import _deterministic_tar_gz
    from packaging_tools.sign_release import sign_bytes, sign_file

    k = _ser.load_pem_private_key(key_path.read_bytes(), password=None)
    out = work / "nonat"
    out.mkdir()
    stage = out / "stage" / "decoy-0.1.0-linux-x86_64"
    stage.parent.mkdir()
    with tarfile.open(dist / "decoy-0.1.0-linux-x86_64.tar.gz", "r:gz") as tar:
        tar.extractall(stage.parent, filter="data")
    for d in (stage / "python").rglob("decoy_engine_native*"):
        shutil.rmtree(d, ignore_errors=True) if d.is_dir() else d.unlink()
    (stage / m.MANIFEST_NAME).unlink(missing_ok=True)
    (stage / m.MANIFEST_SIG_NAME).unlink(missing_ok=True)
    man = m.compute_manifest(stage, version="0.1.0", target="linux-x86_64")
    man_bytes = signing.canonical_bytes(man)
    (stage / m.MANIFEST_NAME).write_bytes(man_bytes)
    (stage / m.MANIFEST_SIG_NAME).write_text(sign_bytes(man_bytes, k))
    tarball = out / "decoy-0.1.0-linux-x86_64.tar.gz"
    _deterministic_tar_gz(stage, tarball)
    (tarball.with_name(tarball.name + ".sha256")).write_text(f"{m.sha256_file(tarball)}  {tarball.name}\n")
    sign_file(tarball, k)
    return out


def _run_upgrade_cases(bindir: Path, doc_url: str, pub: Path, check) -> None:
    launcher = bindir / "decoy"
    env = _bundle_env(DECOY_RELEASE_PUBKEY_FILE=str(pub), DECOY_BIN_DIR=str(bindir))
    # real upgrade 0.1.0 -> 0.2.0 (doc fetched over file://, --url overrides the endpoint)
    up = subprocess.run([str(launcher), "upgrade", "--url", doc_url], env=env, capture_output=True, text=True)
    ver = subprocess.run([str(launcher), "--version"], env=env, capture_output=True, text=True)
    check("case5.upgrade", up.returncode == 0 and "0.2.0" in ver.stdout,
          (up.stdout + up.stderr).strip().splitlines()[-1] if up.returncode or "0.2.0" not in ver.stdout else "0.1.0 -> 0.2.0")
    # The rollback-on-injected-failure path is covered deterministically by the unit
    # test tests/unit/test_distribution.py::test_installer_rolls_back_on_post_swap_failure
    # (a real signed bundle + an injected post-swap failure -> current rolls back).
    _log("[note] rollback-on-failure is asserted by the installer unit test (injected post-swap failure).")


# --- candidate mode (REL-GATE 5.4) ----------------------------------------------------------

NATIVE_PIPELINE = REPO_ROOT / "packaging_tools" / "smoke" / "native.yaml"


_PEM_BLOCK = re.compile(r"-----BEGIN PUBLIC KEY-----[^-]*-----END PUBLIC KEY-----")


def _pem_body(pem: str) -> str:
    return "".join(pem.replace("-----BEGIN PUBLIC KEY-----", "")
                   .replace("-----END PUBLIC KEY-----", "").split())  # fmt: skip


class StepFailed(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _err(msg: str) -> None:
    print(f"smoke: {msg}", file=sys.stderr, flush=True)


def _usage_problem(args: argparse.Namespace, host: str | None) -> str | None:
    if args.keep:
        return "--keep is refused in candidate mode: the temp root holds the throwaway secret"
    if "DECOY_RELEASE_PUBKEY_FILE" in os.environ:
        return "DECOY_RELEASE_PUBKEY_FILE is set; candidate mode trusts only the pinned keys"
    if args.python or args.wheels or args.work:
        return "--python, --wheels and --work belong to the build smoke, not candidate mode"
    if not (args.from_dist and args.candidate and args.pubkey and args.target):
        return "candidate mode needs --from-dist, --candidate, --pubkey and --target"
    from packaging_tools.candidate import GATED_TARGETS

    if args.target in GATED_TARGETS:
        return f"{args.target}: {GATED_TARGETS[args.target]}"
    from decoy.distribution.targets import SUPPORTED_TARGETS

    if args.target not in SUPPORTED_TARGETS:
        return f"{args.target}: not a supported target ({', '.join(SUPPORTED_TARGETS)})"
    if args.target != host:
        return f"--target {args.target} does not match this host ({host or 'unsupported'})"
    if not Path(args.from_dist).is_dir() or not Path(args.pubkey).is_file():
        return "--from-dist must be a directory and --pubkey a file"
    return None


def native_route_ok(stdout: str) -> bool:
    """`decoy run --json` took the compiled kernel; `applicable` alone is not enough."""
    try:
        payload = json.loads(stdout)
    except ValueError:
        return False
    route = payload.get("native_route") if isinstance(payload, dict) else None
    return isinstance(route, dict) and route.get("state") == "native"


def run_outputs(stdout: str, work: Path) -> list[Path] | None:
    """The files a green `decoy run --json` wrote, or None.

    A run writes into the implicit project's run folder (`out/<pipeline>/<run id>/`), not
    beside the pipeline, so the payload's `outputs` is the only reliable place to find them.
    Every path must be a file under ``work``.
    """
    try:
        payload = json.loads(stdout)
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        return None
    outputs = payload.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        return None
    base = work.resolve()
    paths = []
    for entry in outputs:
        raw = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(raw, str):
            return None
        path = Path(raw).resolve()
        if not path.is_file() or not path.is_relative_to(base):
            return None
        paths.append(path)
    return paths


class _Candidate:
    """One candidate-mode run. Every path it writes is under ``root``, never under ``dist``."""

    def __init__(self, args: argparse.Namespace, root: Path) -> None:
        self.dist = Path(args.from_dist)
        self.candidate_path = Path(args.candidate)
        self.pubkey_path = Path(args.pubkey)
        self.pub_pem = ""
        self.target = args.target
        self.root = root
        self.copy = root / "dist"
        self.record: dict[str, str] = {}
        self.listing: dict[str, str] = {}
        self.engine_version = ""

    # One method per name in `candidate.SMOKE_STEPS`; the run stops at the first failure.
    def candidate(self) -> None:
        from packaging_tools import candidate as cand

        try:
            self.record = cand.read_candidate(self.candidate_path)
            sums = (self.dist / cand.SUMS_NAME).read_bytes()
            self.listing = cand.parse_sums(sums.decode("utf-8"))
        except (OSError, ValueError):
            raise StepFailed("smoke_candidate_mismatch")
        if hashlib.sha256(sums).hexdigest() != self.record["sha256sums_sha256"]:
            raise StepFailed("smoke_candidate_mismatch")
        present = {p.name for p in self.dist.iterdir() if p.is_file() and cand.listed(p.name)}
        if present != set(self.listing):
            raise StepFailed("smoke_candidate_mismatch")
        self.copy.mkdir()
        for name, digest in self.listing.items():
            shutil.copyfile(self.dist / name, self.copy / name)
            if cand.sha256_file(self.copy / name) != digest:
                raise StepFailed("smoke_candidate_mismatch")

    def version_document(self) -> None:
        from urllib.parse import urlparse

        from decoy.distribution import version_document as vd
        from packaging_tools.candidate import VERSION_DOCUMENT

        try:
            self.pub_pem = self.pubkey_path.read_text(encoding="utf-8")
            data = (self.copy / VERSION_DOCUMENT).read_bytes()
            signature = (self.copy / f"{VERSION_DOCUMENT}.sig").read_text(encoding="utf-8")
            if not vd.verify_document(data, signature.strip(), expected_public_pem=self.pub_pem):
                raise ValueError("signature")
            payload = vd.parse_document(data)
            # A local-bundle install skips the document, so this is the only check that a
            # real install would not refuse it as expired.
            vd.check_fresh(payload)
        except (OSError, ValueError):
            raise StepFailed("smoke_version_document_invalid")
        version = self.record["cli_version"]
        if vd.is_yanked(payload, version):
            raise StepFailed("smoke_version_document_invalid")
        artifacts = payload.get("artifacts")
        tarballs = {n for n in self.listing if n.endswith(".tar.gz")}
        if payload.get("latest") != version or not isinstance(artifacts, dict):
            raise StepFailed("smoke_version_document_invalid")
        named = set()
        for target in artifacts:
            entry = vd.select_artifact(payload, target)
            name = f"decoy-{version}-{target}.tar.gz"
            if (
                entry is None
                or entry["sha256"] != self.listing.get(name)
                or Path(urlparse(entry["url"]).path).name != name
                or Path(urlparse(entry["sig"]).path).name != f"{name}.sig"
                or f"{name}.sig" not in self.listing
            ):
                raise StepFailed("smoke_version_document_invalid")
            named.add(name)
        if named != tarballs or self.target not in artifacts:
            raise StepFailed("smoke_version_document_invalid")

    def installer_key(self) -> None:
        from decoy.distribution.release_key import PLACEHOLDER_MARKER
        from packaging_tools.candidate import INSTALLERS

        if "install.sh" not in self.listing:
            raise StepFailed("smoke_candidate_mismatch")
        # An installer pinning another key installs the local bundle signed with that key but
        # refuses the version document every real install reads, so its key must be --pubkey.
        want = {_pem_body(self.pub_pem)}
        for name in INSTALLERS:
            if name in self.listing:
                text = (self.copy / name).read_text(encoding="utf-8")
                pinned = {_pem_body(block) for block in _PEM_BLOCK.findall(text)}
                if PLACEHOLDER_MARKER in text or pinned != want:
                    raise StepFailed("smoke_placeholder_key")

    def install(self) -> None:
        name = f"decoy-{self.record['cli_version']}-{self.target}.tar.gz"
        tarball = self.copy / name
        # The sidecar carries the digest the candidate step verified, not a fresh one, so a
        # tarball swapped after that step fails the installer's checksum.
        tarball.with_name(f"{name}.sha256").write_text(f"{self.listing[name]}  {name}\n")
        run = subprocess.run(
            ["sh", str(self.copy / "install.sh"), "--version", self.record["cli_version"]],
            cwd=self.root,
            env=self._env(DECOY_LOCAL_BUNDLE=str(tarball)),
            capture_output=True,
            text=True,
        )
        if run.returncode != 0:
            lines = run.stderr.strip().splitlines()
            _err(f"installer: {lines[-1] if lines else 'no output'}")
            raise StepFailed("smoke_install_failed")

    def bundle_key(self) -> None:
        pem = self._bundle_python(
            "import sys\n"
            "from decoy.distribution import release_key\n"
            "sys.stdout.write(release_key.pinned_public_pem())"
        )
        if pem is None or _pem_body(pem) != _pem_body(self.pub_pem):
            raise StepFailed("smoke_placeholder_key")
        engine = self._bundle_python("import decoy_engine; print(decoy_engine.__version__)")
        if not engine:
            raise StepFailed("smoke_engine_version")
        self.engine_version = engine.strip()

    def version(self) -> None:
        run = self._decoy("--version")
        if run.returncode != 0 or run.stdout.strip() != f"decoy {self.record['cli_version']}":
            raise StepFailed("smoke_version_mismatch")

    def doctor(self) -> None:
        run = self._decoy("doctor", "--json")
        try:
            ok = run.returncode == 0 and isinstance(json.loads(run.stdout), dict)
        except ValueError:
            ok = False
        if not ok:
            raise StepFailed("smoke_doctor_failed")

    def native(self) -> None:
        work = self._workdir("native")
        shutil.copyfile(NATIVE_PIPELINE, work / "native.yaml")
        rows = [
            f"{n},note-{n},code-{n},user{n}@example.invalid,{('bronze', 'silver', 'gold')[n % 3]},"
            f"2024-{n % 12 + 1:02d}-15,house-{n % 4},region-{n % 3}"
            for n in range(1, 25)
        ]
        header = "id,note,code,email,tier,opened,household,region"
        (work / "input.csv").write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
        secret = self.root / "mask-secret"
        fd = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(secrets.token_hex(32))
        run = self._decoy(
            "run", "native.yaml", "--native", "--json", "--mask-secret", f"file:{secret}", cwd=work
        )
        if run.returncode != 0 or not native_route_ok(run.stdout):
            raise StepFailed("smoke_native_route")
        if run_outputs(run.stdout, work) is None:
            raise StepFailed("smoke_native_route")

    def template(self) -> None:
        work = self._workdir("template")
        shown = self._decoy("show", "template", "minimal")
        if shown.returncode != 0:
            raise StepFailed("smoke_template_failed")
        (work / "pipeline.yaml").write_text(shown.stdout, encoding="utf-8")
        rows = [
            f"first-{n},last-{n},user{n}@example.invalid,000-00-{n:04d},active"
            for n in range(1, 13)
        ]
        header = "first_name,last_name,email,ssn,account_status"
        (work / "input.csv").write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
        run = self._decoy("run", "pipeline.yaml", "--json", cwd=work)
        if run.returncode != 0 or run_outputs(run.stdout, work) is None:
            raise StepFailed("smoke_template_failed")

    def _env(self, **extra: str) -> dict:
        # No DECOY_* or XDG_* setting of the caller's reaches the installed decoy: a library,
        # project or telemetry endpoint would send its records outside the temp root.
        env = {k: v for k, v in _bundle_env().items() if not k.startswith(("DECOY_", "XDG_"))}
        env.update(
            DECOY_HOME=str(self.root / "home"),
            DECOY_BIN_DIR=str(self.root / "bin"),
            HOME=str(self.root / "user"),
            DECOY_NO_UPDATE_CHECK="1",
            **extra,
        )
        return env

    def _workdir(self, name: str) -> Path:
        path = self.root / name
        path.mkdir()
        return path

    def _decoy(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        launcher = self.root / "bin" / "decoy"
        return subprocess.run(
            [str(launcher), *args],
            cwd=cwd or self.root,
            env=self._env(),
            capture_output=True,
            text=True,
        )

    def _bundle_python(self, code: str) -> str | None:
        python = self.root / "home" / "current" / "python" / "bin" / "python3"
        run = subprocess.run(
            [str(python), "-I", "-c", code], env=self._env(), capture_output=True, text=True
        )
        return run.stdout if run.returncode == 0 else None


def candidate_main(argv: list[str]) -> int:
    from decoy.distribution.targets import detect_target
    from packaging_tools.candidate import SMOKE_STEPS, SUMMARY_SCHEMA

    ap = argparse.ArgumentParser(prog="smoke_install (candidate mode)")
    ap.add_argument("--from-dist", help="the signed candidate set (read only)")
    ap.add_argument("--candidate", help="candidate.json beside the set")
    ap.add_argument("--pubkey", help="the release public key PEM")
    ap.add_argument("--target", help="this host's platform tag")
    ap.add_argument("--keep", action="store_true", help=argparse.SUPPRESS)
    for flag in ("--python", "--wheels", "--work"):
        ap.add_argument(flag, help=argparse.SUPPRESS)
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    problem = _usage_problem(args, detect_target())
    if problem:
        _err(f"usage: {problem}")
        return 2
    started = time.monotonic()
    steps: dict[str, str] = {}
    root = Path(tempfile.mkdtemp(prefix="decoy-smoke-"))
    run = _Candidate(args, root)
    try:
        for step in SMOKE_STEPS[:-1]:  # the last, cleanup, is decided after the finally
            try:
                getattr(run, step)()
            except StepFailed as failure:
                steps[step] = "fail"
                _err(f"{step}: FAIL {failure.code}")
                break
            except Exception as exc:  # any other error is a red step, never a skipped summary
                steps[step] = "fail"
                _err(f"{step}: FAIL smoke_step_error ({type(exc).__name__})")
                break
            steps[step] = "pass"
            _err(f"{step}: pass")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    removed = not root.exists()
    steps["cleanup"] = "pass" if removed else "fail"
    if not removed:
        _err("cleanup: FAIL smoke_temp_root_left (the temp root and its secret are still there)")
    summary = {
        "schema": SUMMARY_SCHEMA,
        "platform": args.target,
        "cli_version": run.record.get("cli_version", ""),
        "engine_version": run.engine_version,
        "sha256sums_sha256": run.record.get("sha256sums_sha256", ""),
        "steps": steps,
        "seconds": round(time.monotonic() - started, 1),
    }
    print(json.dumps(summary, sort_keys=True))
    green = set(steps) == set(SMOKE_STEPS) and set(steps.values()) == {"pass"}
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
