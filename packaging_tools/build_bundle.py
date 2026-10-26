"""Deterministic per-target bundle assembler (build host only).

Produces one self-contained bundle for a target: a standalone CPython (a
python-build-standalone distribution, the portable interpreter `uv`/`rye` ship) with
the matched `decoy-engine` + `decoy-engine-native` + `decoy-cli` wheels installed into
it, plus a `decoy` launcher that runs the interpreter as ``python -m decoy``. The
bundle carries a signed checksum manifest (`decoy.distribution.manifest` + the release key),
and is packed into a reproducible ``.tar.gz`` with a ``.sha256`` and a detached
``.sig``.

Established pattern (packaging spec "Established solutions"): managed self-contained
install = embedded python-build-standalone + a launcher, the uv/rye/rustup model; the
compiled companion is consumed from the already-green native wheel matrix
(`decoy-engine/.github/workflows/native-companion.yml`), never rebuilt here.

Determinism: the launcher uses ``python -m decoy`` (never the pip console-script, whose
shebang would embed the build-host path), generated console-script shebangs under
``python/bin`` are normalized, ``__pycache__`` is dropped, and the tar is written with
sorted entries and a fixed mtime/uid/gid/mode, so the same inputs yield byte-identical
archive bytes. The interpreter's own contents are whatever python-build-standalone
shipped (hashed into the manifest, not rewritten).
"""

from __future__ import annotations

import argparse
import io
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from decoy.distribution import manifest as manifest_mod
from decoy.distribution.signing import canonical_bytes

# Fixed metadata for reproducible archives (the epoch many reproducible-build
# toolchains use; any constant works as long as it is constant).
_FIXED_MTIME = 1_700_000_000
_LAUNCHER = """\
#!/bin/sh
# Decoy managed-runtime launcher. Resolves the bundle dir from its own location
# (pwd -P follows the `current` symlink to the real versions/<v> dir), then runs
# the bundled interpreter as `python -m decoy`. Never relies on a pip console-script
# shebang, which would embed the build-host path.
#
# The managed interpreter runs IMPORT-ISOLATED and bytecode-free: -I -B.
#
# -I (isolated mode) drops the current working directory and the script dir from
# sys.path and ignores PYTHONPATH/PYTHON* env, so running `decoy` from inside a
# downloaded project that ships its own `decoy/` package (or a planted top-level
# module) cannot shadow the signed, verified runtime: imports resolve only from the
# bundle's own site. Without -I, a hostile CWD or PYTHONPATH would execute attacker
# code in place of the signed installation.
#
# -B stops bytecode writes: the runtime must never create a __pycache__/.pyc beside
# the signed, verified source, because an unsigned cache is not covered by the bundle
# manifest and Python's default timestamp-based cache invalidation would load a forged
# .pyc in place of the source. With writing off, every import compiles from the signed
# source and `verify_extracted` (which rejects any cache found on disk) stays
# authoritative for rollback/activation. -I ignores the PYTHONDONTWRITEBYTECODE env
# var, so the explicit -B flag is what guarantees this for the managed interpreter; the
# env export below still shields any non-isolated child process.
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
PYTHONDONTWRITEBYTECODE=1 exec "$here/python/bin/python3" -I -B -m decoy "$@"
"""


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _copy_interpreter(python_src: Path, dest: Path) -> None:
    """Copy the standalone interpreter tree into ``dest`` (dereferencing the top-level
    convenience symlink uv leaves)."""
    real = python_src.resolve()
    shutil.copytree(real, dest, symlinks=True)


def _clear_externally_managed(python_dir: Path) -> None:
    """Drop the EXTERNALLY-MANAGED marker in the embedded interpreter. This is Decoy's
    OWN managed runtime, not a system or user environment, so pip installing into it is
    exactly what it is for (PEP 668's marker is aimed at the user's system Python)."""
    for marker in python_dir.rglob("EXTERNALLY-MANAGED"):
        marker.unlink()


def _install_wheels(python_bin: Path, wheels_dir: Path, version: str) -> None:
    """Install the matched wheels OFFLINE from ``wheels_dir`` (no index), so the bundle
    pins exactly the wheels handed to the build and resolves NOTHING from the network.
    ``wheels_dir`` must already hold the full dependency closure (the release pipeline
    populates it; see packaging_tools/README.md)."""
    _run(
        [
            str(python_bin),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-compile",
            "--find-links",
            str(wheels_dir),
            f"decoy-cli=={version}",
            "decoy-engine",
            "decoy-engine-native",
        ]
    )


def _normalize_bin_shebangs(bin_dir: Path, stage_python: Path) -> None:
    """Rewrite console-script shebangs that embed the build-host interpreter path to a
    host-independent form. The launcher does not use these scripts, but normalizing them
    keeps the bundle byte-reproducible across build hosts."""
    marker = f"#!{stage_python}".encode()
    for entry in sorted(bin_dir.iterdir()):
        if not entry.is_file() or entry.is_symlink():
            continue
        try:
            head = entry.read_bytes()
        except OSError:
            continue
        if head.startswith(marker):
            rest = head[len(marker) :]
            entry.write_bytes(b"#!/usr/bin/env python3" + rest)


def _strip_pycache(root: Path) -> None:
    for pc in sorted(root.rglob("__pycache__")):
        shutil.rmtree(pc, ignore_errors=True)


def _write_launcher(stage: Path) -> None:
    launcher = stage / "decoy"
    launcher.write_text(_LAUNCHER, encoding="utf-8")
    launcher.chmod(0o755)


def _write_bundle_info(stage: Path, *, version: str, target: str) -> None:
    info = {"schema_version": "cli-bundle-info/v1", "version": version, "target": target}
    (stage / "BUNDLE_INFO.json").write_bytes(canonical_bytes(info))


def _deterministic_tar_gz(stage: Path, out_path: Path) -> None:
    """Write a reproducible .tar.gz of ``stage`` (sorted entries, fixed mtime/uid/gid,
    normalized modes, no gzip mtime). Top-level dir in the archive is the bundle name."""
    top = out_path.name
    for suffix in (".tar.gz", ".tgz"):
        if top.endswith(suffix):
            top = top[: -len(suffix)]
            break

    members: list[tuple[str, Path]] = []
    for p in sorted(stage.rglob("*"), key=lambda x: x.relative_to(stage).as_posix()):
        members.append((f"{top}/{p.relative_to(stage).as_posix()}", p))

    def _reset(ti: tarfile.TarInfo) -> tarfile.TarInfo:
        ti.mtime = _FIXED_MTIME
        ti.uid = ti.gid = 0
        ti.uname = ti.gname = ""
        if ti.isdir():
            ti.mode = 0o755
        elif ti.mode & 0o111:
            ti.mode = 0o755
        else:
            ti.mode = 0o644
        return ti

    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for arcname, path in members:
            ti = tar.gettarinfo(str(path), arcname=arcname)
            ti = _reset(ti)
            if path.is_symlink():
                tar.addfile(ti)
            elif path.is_file():
                with open(path, "rb") as fh:
                    tar.addfile(ti, fh)
            else:
                tar.addfile(ti)
    import gzip

    with open(out_path, "wb") as fh:
        # mtime=0 so the gzip header carries no build timestamp.
        with gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0) as gz:
            gz.write(raw.getvalue())


def build_bundle(
    *,
    version: str,
    target: str,
    python_src: Path,
    wheels_dir: Path,
    out_dir: Path,
    private_key=None,
) -> dict[str, Path]:
    """Assemble + (optionally) sign one bundle. Returns {stage, tarball, sha256, sig?}.

    When ``private_key`` is given the in-bundle manifest and the tarball are signed;
    without it (a dry/unsigned build) the manifest is written unsigned and no tarball
    signature is produced -- useful for a local smoke that does its own signing."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stage = out_dir / f"decoy-{version}-{target}"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    python_dir = stage / "python"
    _copy_interpreter(python_src, python_dir)
    _clear_externally_managed(python_dir)
    python_bin = python_dir / "bin" / "python3"
    _install_wheels(python_bin, wheels_dir, version)
    _normalize_bin_shebangs(python_dir / "bin", python_bin)
    _strip_pycache(stage)
    _write_launcher(stage)
    _write_bundle_info(stage, version=version, target=target)

    man = manifest_mod.compute_manifest(stage, version=version, target=target)
    man_bytes = canonical_bytes(man)
    (stage / manifest_mod.MANIFEST_NAME).write_bytes(man_bytes)
    if private_key is not None:
        from packaging_tools.sign_release import sign_bytes

        (stage / manifest_mod.MANIFEST_SIG_NAME).write_text(
            sign_bytes(man_bytes, private_key) + "\n", encoding="utf-8"
        )

    tarball = out_dir / f"decoy-{version}-{target}.tar.gz"
    _deterministic_tar_gz(stage, tarball)
    sha = manifest_mod.sha256_file(tarball)
    sha_path = tarball.with_name(tarball.name + ".sha256")
    sha_path.write_text(f"{sha}  {tarball.name}\n", encoding="utf-8")

    result = {"stage": stage, "tarball": tarball, "sha256": sha_path}
    if private_key is not None:
        from packaging_tools.sign_release import sign_file

        result["sig"] = sign_file(tarball, private_key)
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="build_bundle")
    ap.add_argument("--version", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--python", required=True, help="standalone CPython dir to embed")
    ap.add_argument("--wheels", required=True, help="dir with the three matched wheels")
    ap.add_argument("--out", required=True, help="output dir for the bundle + archive")
    ap.add_argument("--sign", action="store_true", help="sign manifest + tarball with the release key")
    args = ap.parse_args(argv)

    # Only assemble targets in the advertised matrix. Windows is gated off this cycle
    # (POSIX-shaped runtime, lifecycle unverified); building one would produce an
    # unrunnable advertised path. See decoy.distribution.targets.
    from decoy.distribution import targets as targets_mod

    if args.target not in targets_mod.SUPPORTED_TARGETS:
        supported = ", ".join(targets_mod.SUPPORTED_TARGETS)
        sys.stderr.write(
            f"refusing to build: {args.target!r} is not in the advertised matrix ({supported})\n"
        )
        return 2

    key = None
    if args.sign:
        from packaging_tools.sign_release import load_private_key

        key = load_private_key()

    result = build_bundle(
        version=args.version,
        target=args.target,
        python_src=Path(args.python),
        wheels_dir=Path(args.wheels),
        out_dir=Path(args.out),
        private_key=key,
    )
    for k, v in result.items():
        sys.stderr.write(f"{k}: {v}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
