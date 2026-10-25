"""Per-platform bundle assembler.

Assembles one self-contained bundle for one target: an embedded standalone
CPython, a private venv with the matched engine + native companion + CLI wheels,
and a `decoy` launcher. The layout is the versioned directory that the installer
lays down under `~/.decoy/versions/<version>/` and points `current` at, so an
upgrade is an atomic symlink swap (the model uv / rye / rustup use; see the build
plan's "Established solutions").

The heavy fetches (the standalone CPython distribution, the built wheels) are
INPUTS, not something this module does: the standalone interpreter comes from
python-build-standalone and the wheels come from the engine's already-green
native matrix (`native-companion.yml`). This module takes their paths and
assembles the bundle, and it can `plan()` the whole layout and validate the
version matching without touching disk, so the matching rules are unit-testable
without a 600 MB download.

The one invariant this module enforces hard: a bundle's engine and native
companion wheels are the SAME version (one build, split into two wheels), that
version equals the launch engine pin (`packaging/pin.env`), the native wheel's
platform tag is compatible with the target, and the CLI wheel equals the CLI pin.
A mismatch raises `BundleSpecError` and nothing is assembled. That is the
"versions in one bundle must match" acceptance, checked in one place.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

# Relative import on purpose: the operator tree is named `packaging/`, which must
# never shadow the real `packaging` PyPI library (PEP 440, used by the version
# client). So `bundle` is imported as its own top-level package (tests add
# `packaging/` to the path, not the repo root), and never as `packaging.bundle`.
from .targets import Target, target_for_key

_PIN_FILE = Path(__file__).resolve().parents[1] / "pin.env"


class BundleSpecError(Exception):
    """A bundle spec that fails the matched-version / matched-target invariant.

    Raised by `plan()` before any disk I/O, so a mismatched or mislabeled wheel
    set never produces a half-built or wrongly-matched bundle."""


def read_pins(pin_file: Path | None = None) -> dict[str, str]:
    """Parse `packaging/pin.env` as KEY=VALUE lines. No shell is invoked.

    One place per fact: this is the only reader of the launch pins on the Python
    side (the shell tools `source` the same file). Comment lines (`#`) and blank
    lines are skipped; a value keeps everything after the first `=`."""
    path = pin_file or _PIN_FILE
    pins: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        pins[key.strip()] = value.strip()
    return pins


@dataclass(frozen=True)
class Wheel:
    """A built wheel, parsed from its PEP 427 filename.

    `platform_tag` is the last filename segment (`any`, `manylinux_2_28_x86_64`,
    `win_amd64`, `macosx_11_0_arm64`, ...); it is what decides whether a native
    wheel belongs to a target."""

    path: Path
    distribution: str
    version: str
    platform_tag: str

    @classmethod
    def from_path(cls, path: Path) -> "Wheel":
        stem = path.name[:-4] if path.name.endswith(".whl") else path.name
        parts = stem.split("-")
        if len(parts) < 5:
            raise BundleSpecError(
                f"not a PEP 427 wheel filename: {path.name!r} "
                "(expected dist-version-pytag-abitag-platformtag.whl)"
            )
        # PEP 427: an optional build tag can sit between version and pytag, so the
        # distribution + version are the FIRST two fields and the platform tag is
        # the LAST field; the middle count varies. Normalize the distribution the
        # way pip does (underscores and hyphens are equivalent) so `decoy_engine`
        # and `decoy-engine` compare equal.
        distribution = parts[0].replace("_", "-").lower()
        version = parts[1]
        platform_tag = parts[-1]
        return cls(path=path, distribution=distribution, version=version, platform_tag=platform_tag)


@dataclass(frozen=True)
class BundleSpec:
    """Everything one bundle is assembled from.

    `cpython_src` is a path to an already-extracted standalone CPython directory
    for the target; `wheels` are the built wheel files to install into the
    embedded venv. In an offline / fake assembly (`install_wheels=False`) the
    wheels are recorded in the manifest but not pip-installed, which is what lets
    the layout + launcher + manifest be produced and tested without the real
    interpreter or network."""

    target: Target
    cpython_src: Path
    wheels: tuple[Wheel, ...]
    output_root: Path
    install_wheels: bool = True

    @classmethod
    def build(
        cls,
        *,
        target_key: str,
        cpython_src: Path,
        wheel_paths: list[Path],
        output_root: Path,
        install_wheels: bool = True,
    ) -> "BundleSpec":
        return cls(
            target=target_for_key(target_key),
            cpython_src=Path(cpython_src),
            wheels=tuple(Wheel.from_path(Path(p)) for p in wheel_paths),
            output_root=Path(output_root),
            install_wheels=install_wheels,
        )


@dataclass(frozen=True)
class BundlePlan:
    """The validated, resolved layout for one bundle, before anything is written."""

    target: Target
    engine_version: str
    native_version: str
    cli_version: str
    native_abi: str
    python_version: str
    artifact_name: str
    bundle_dir: Path
    wheels: tuple[Wheel, ...] = field(default_factory=tuple)


def _find_one(wheels: tuple[Wheel, ...], distribution: str) -> Wheel:
    matches = [w for w in wheels if w.distribution == distribution]
    if not matches:
        raise BundleSpecError(
            f"bundle is missing the {distribution!r} wheel; a bundle must carry the "
            "matched engine, native companion, and CLI wheels"
        )
    if len(matches) > 1:
        names = ", ".join(sorted(w.path.name for w in matches))
        raise BundleSpecError(f"more than one {distribution!r} wheel in the set: {names}")
    return matches[0]


# A native wheel's platform tag must name the target's architecture. The
# python-build-standalone triple carries the arch (x86_64 / aarch64 / arm64), and
# the wheel platform tag carries it too (manylinux_2_28_x86_64, win_amd64,
# macosx_11_0_arm64); this maps a target to the arch token(s) its native wheel
# tag must contain. win_amd64 is x86_64 under another name, so it is listed.
_TARGET_ARCH_TOKENS: dict[str, tuple[str, ...]] = {
    "linux-x86_64": ("x86_64",),
    "linux-aarch64": ("aarch64",),
    "windows-x86_64": ("amd64", "x86_64"),
    "macos-arm64": ("arm64",),
}


def plan(spec: BundleSpec, pin_file: Path | None = None) -> BundlePlan:
    """Validate the matched-version / matched-target invariant and resolve the
    layout. Pure apart from reading `pin.env`; raises `BundleSpecError` on any
    mismatch so a bad wheel set never reaches disk."""
    pins = read_pins(pin_file)
    pin_engine = pins["DECOY_LAUNCH_ENGINE_VERSION"]
    pin_cli = pins["DECOY_LAUNCH_CLI_VERSION"]
    native_abi = pins["DECOY_LAUNCH_NATIVE_ABI"]
    python_version = pins["DECOY_LAUNCH_PYTHON_VERSION"]

    engine = _find_one(spec.wheels, "decoy-engine")
    native = _find_one(spec.wheels, "decoy-engine-native")
    cli = _find_one(spec.wheels, "decoy-cli")

    # The load-bearing invariant: engine and native are one build (equal
    # versions), and that version is the launch pin. A drift here is exactly the
    # "pip paired a different-ABI engine with the companion" failure the
    # self-hosted bundle exists to prevent.
    if engine.version != native.version:
        raise BundleSpecError(
            "engine / native companion version mismatch in one bundle: "
            f"decoy-engine=={engine.version} but decoy-engine-native=={native.version}; "
            "they are one build and must be the same version"
        )
    if engine.version != pin_engine:
        raise BundleSpecError(
            f"bundle engine version {engine.version} does not match the launch pin "
            f"{pin_engine} (packaging/pin.env DECOY_LAUNCH_ENGINE_VERSION); rebuild "
            "against the pinned engine or swap the pin"
        )
    if cli.version != pin_cli:
        raise BundleSpecError(
            f"bundle CLI version {cli.version} does not match the launch pin "
            f"{pin_cli} (packaging/pin.env DECOY_LAUNCH_CLI_VERSION)"
        )

    # The native wheel must be built for this target's architecture (a
    # platform-tagged wheel, never `any`). A linux-aarch64 bundle carrying the
    # x86_64 companion would install and then fail to load at run time; catch it
    # at assembly.
    if native.platform_tag == "any":
        raise BundleSpecError(
            f"native companion wheel {native.path.name!r} is platform-independent "
            "(`any`); a native wheel must be built for a specific target"
        )
    tokens = _TARGET_ARCH_TOKENS[spec.target.key]
    if not any(token in native.platform_tag for token in tokens):
        raise BundleSpecError(
            f"native companion wheel {native.path.name!r} (platform tag "
            f"{native.platform_tag!r}) does not match target {spec.target.key!r} "
            f"(expected one of {tokens} in the platform tag)"
        )

    artifact_name = f"decoy-{cli.version}-{spec.target.key}.tar.gz"
    bundle_dir = spec.output_root / cli.version / spec.target.key
    return BundlePlan(
        target=spec.target,
        engine_version=engine.version,
        native_version=native.version,
        cli_version=cli.version,
        native_abi=native_abi,
        python_version=python_version,
        artifact_name=artifact_name,
        bundle_dir=bundle_dir,
        wheels=spec.wheels,
    )


_LAUNCHER_DIR = Path(__file__).resolve().parent / "launcher"


def _manifest(plan_: BundlePlan) -> dict:
    return {
        "schema_version": 1,
        "target": plan_.target.key,
        "cli_version": plan_.cli_version,
        "engine_version": plan_.engine_version,
        "native_version": plan_.native_version,
        "native_abi_expected": plan_.native_abi,
        "python_version": plan_.python_version,
        "wheels": sorted(w.path.name for w in plan_.wheels),
        # The launcher sets this; recorded here so the smoke step and the
        # installer can both confirm a bundle is a managed runtime.
        "managed_runtime": True,
    }


def assemble(spec: BundleSpec, pin_file: Path | None = None) -> BundlePlan:
    """Plan, then lay the bundle down on disk and return the plan.

    Writes the versioned bundle directory: the embedded CPython, the launcher,
    the bundle manifest, and (when `spec.install_wheels`) the matched wheels
    installed into the embedded venv via the embedded interpreter's own pip. The
    per-target smoke (`decoy doctor`, a real mask, the native-route assertion)
    runs against the result and is driven by the build pipeline, not here."""
    plan_ = plan(spec, pin_file)
    bundle_dir = plan_.bundle_dir
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True)

    python_dir = bundle_dir / "python"
    shutil.copytree(spec.cpython_src, python_dir)

    wheels_dir = bundle_dir / "wheels"
    wheels_dir.mkdir()
    for wheel in spec.wheels:
        shutil.copy2(wheel.path, wheels_dir / wheel.path.name)

    if spec.install_wheels:
        _pip_install_into_embedded_venv(python_dir, wheels_dir, plan_)

    _write_launcher(bundle_dir, spec.target)
    (bundle_dir / "bundle-manifest.json").write_text(
        json.dumps(_manifest(plan_), indent=2) + "\n", encoding="utf-8"
    )
    return plan_


def _pip_install_into_embedded_venv(python_dir: Path, wheels_dir: Path, plan_: BundlePlan) -> None:
    """Install the matched wheels into a private venv under the embedded CPython.

    Uses the embedded interpreter's own pip against the local wheel directory
    with `--no-index`, so the install resolves only the bundled wheels and never
    reaches a package index (the bundle is self-contained by construction). Kept
    as its own function so the offline/fake assembly path can skip exactly this
    one step and still produce a real, inspectable layout."""
    import subprocess
    import sys

    # The embedded interpreter's layout differs per OS (bin/python3 on
    # posix, python.exe on Windows); the build pipeline runs this on the
    # matching host, so resolve the interpreter from the standard locations.
    candidates = [
        python_dir / "bin" / "python3",
        python_dir / "bin" / "python",
        python_dir / "python.exe",
        python_dir / "python",
    ]
    interpreter = next((c for c in candidates if c.exists()), None)
    if interpreter is None:
        raise BundleSpecError(
            f"no embedded interpreter found under {python_dir}; expected one of "
            + ", ".join(str(c.relative_to(python_dir.parent)) for c in candidates)
        )
    venv_dir = python_dir.parent / "venv"
    subprocess.run([str(interpreter), "-m", "venv", str(venv_dir)], check=True)
    venv_python = venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    subprocess.run(
        [
            str(venv_python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(wheels_dir),
            f"decoy-cli=={plan_.cli_version}",
            f"decoy-engine=={plan_.engine_version}",
            f"decoy-engine-native=={plan_.native_version}",
        ],
        check=True,
    )


def _write_launcher(bundle_dir: Path, target: Target) -> None:
    bin_dir = bundle_dir / "bin"
    bin_dir.mkdir(exist_ok=True)
    if target.os_name == "windows":
        shutil.copy2(_LAUNCHER_DIR / "decoy.cmd", bin_dir / "decoy.cmd")
    else:
        launcher = bin_dir / "decoy"
        shutil.copy2(_LAUNCHER_DIR / "decoy", launcher)
        launcher.chmod(0o755)
