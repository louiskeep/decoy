"""Bundle assembler: matched-version / matched-target invariant and layout.

These tests exercise the assembler's planning and on-disk layout without a real
standalone CPython or real wheels: the matching rules are pure (they parse wheel
filenames and read `pin.env`), and the layout path uses a fake interpreter
directory with `install_wheels=False`, so no 600 MB download and no engine are
needed. The real per-target smoke (`decoy doctor`, a real mask, the native-route
assertion) runs in the build pipeline on the matching host.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# The operator tree is `packaging/`; add IT to the path (never the repo root) so
# `bundle` imports as its own top-level package and the real `packaging` PyPI
# library is not shadowed. See packaging/bundle/assemble.py.
_PACKAGING = Path(__file__).resolve().parents[2] / "packaging"
if str(_PACKAGING) not in sys.path:
    sys.path.insert(0, str(_PACKAGING))

from bundle.assemble import (  # noqa: E402
    BundleSpec,
    BundleSpecError,
    assemble,
    plan,
    read_pins,
)


def _pins() -> dict[str, str]:
    return read_pins()


def _wheel_set(tmp_path: Path, *, engine: str, native: str, cli: str, native_tag: str) -> list[Path]:
    names = [
        f"decoy_cli-{cli}-py3-none-any.whl",
        f"decoy_engine-{engine}-py3-none-any.whl",
        f"decoy_engine_native-{native}-cp312-cp312-{native_tag}.whl",
    ]
    paths = []
    for name in names:
        p = tmp_path / name
        p.write_bytes(b"fake wheel")
        paths.append(p)
    return paths


def _fake_cpython(tmp_path: Path) -> Path:
    cp = tmp_path / "cpython"
    (cp / "bin").mkdir(parents=True)
    (cp / "bin" / "python3").write_text("#!/bin/sh\n")
    return cp


def test_plan_accepts_a_matched_set(tmp_path):
    pins = _pins()
    engine = pins["DECOY_LAUNCH_ENGINE_VERSION"]
    cli = pins["DECOY_LAUNCH_CLI_VERSION"]
    wheels = _wheel_set(
        tmp_path, engine=engine, native=engine, cli=cli, native_tag="manylinux_2_28_x86_64"
    )
    spec = BundleSpec.build(
        target_key="linux-x86_64",
        cpython_src=_fake_cpython(tmp_path),
        wheel_paths=wheels,
        output_root=tmp_path / "out",
        install_wheels=False,
    )
    p = plan(spec)
    assert p.engine_version == engine
    assert p.native_version == engine
    assert p.cli_version == cli
    assert p.artifact_name == f"decoy-{cli}-linux-x86_64.tar.gz"


def test_plan_rejects_engine_native_version_skew(tmp_path):
    pins = _pins()
    engine = pins["DECOY_LAUNCH_ENGINE_VERSION"]
    cli = pins["DECOY_LAUNCH_CLI_VERSION"]
    # Native a different version than engine: not one build.
    wheels = _wheel_set(
        tmp_path, engine=engine, native="0.0.1", cli=cli, native_tag="manylinux_2_28_x86_64"
    )
    spec = BundleSpec.build(
        target_key="linux-x86_64",
        cpython_src=_fake_cpython(tmp_path),
        wheel_paths=wheels,
        output_root=tmp_path / "out",
        install_wheels=False,
    )
    with pytest.raises(BundleSpecError, match="version mismatch"):
        plan(spec)


def test_plan_rejects_engine_not_matching_pin(tmp_path):
    pins = _pins()
    cli = pins["DECOY_LAUNCH_CLI_VERSION"]
    wheels = _wheel_set(
        tmp_path, engine="99.99.99", native="99.99.99", cli=cli, native_tag="manylinux_2_28_x86_64"
    )
    spec = BundleSpec.build(
        target_key="linux-x86_64",
        cpython_src=_fake_cpython(tmp_path),
        wheel_paths=wheels,
        output_root=tmp_path / "out",
        install_wheels=False,
    )
    with pytest.raises(BundleSpecError, match="does not match the launch pin"):
        plan(spec)


def test_plan_rejects_native_wheel_for_wrong_target(tmp_path):
    pins = _pins()
    engine = pins["DECOY_LAUNCH_ENGINE_VERSION"]
    cli = pins["DECOY_LAUNCH_CLI_VERSION"]
    # x86_64 companion wheel, but the target is aarch64.
    wheels = _wheel_set(
        tmp_path, engine=engine, native=engine, cli=cli, native_tag="manylinux_2_28_x86_64"
    )
    spec = BundleSpec.build(
        target_key="linux-aarch64",
        cpython_src=_fake_cpython(tmp_path),
        wheel_paths=wheels,
        output_root=tmp_path / "out",
        install_wheels=False,
    )
    with pytest.raises(BundleSpecError, match="does not match target"):
        plan(spec)


def test_plan_rejects_platform_independent_native_wheel(tmp_path):
    pins = _pins()
    engine = pins["DECOY_LAUNCH_ENGINE_VERSION"]
    cli = pins["DECOY_LAUNCH_CLI_VERSION"]
    wheels = [
        tmp_path / f"decoy_cli-{cli}-py3-none-any.whl",
        tmp_path / f"decoy_engine-{engine}-py3-none-any.whl",
        tmp_path / f"decoy_engine_native-{engine}-py3-none-any.whl",
    ]
    for p in wheels:
        p.write_bytes(b"fake")
    spec = BundleSpec.build(
        target_key="linux-x86_64",
        cpython_src=_fake_cpython(tmp_path),
        wheel_paths=wheels,
        output_root=tmp_path / "out",
        install_wheels=False,
    )
    with pytest.raises(BundleSpecError, match="platform-independent"):
        plan(spec)


def test_plan_rejects_missing_wheel(tmp_path):
    pins = _pins()
    engine = pins["DECOY_LAUNCH_ENGINE_VERSION"]
    cli = pins["DECOY_LAUNCH_CLI_VERSION"]
    # No native wheel in the set.
    wheels = [
        tmp_path / f"decoy_cli-{cli}-py3-none-any.whl",
        tmp_path / f"decoy_engine-{engine}-py3-none-any.whl",
    ]
    for p in wheels:
        p.write_bytes(b"fake")
    spec = BundleSpec.build(
        target_key="linux-x86_64",
        cpython_src=_fake_cpython(tmp_path),
        wheel_paths=wheels,
        output_root=tmp_path / "out",
        install_wheels=False,
    )
    with pytest.raises(BundleSpecError, match="missing the 'decoy-engine-native' wheel"):
        plan(spec)


def test_assemble_lays_down_layout_and_manifest(tmp_path):
    pins = _pins()
    engine = pins["DECOY_LAUNCH_ENGINE_VERSION"]
    cli = pins["DECOY_LAUNCH_CLI_VERSION"]
    wheels = _wheel_set(
        tmp_path, engine=engine, native=engine, cli=cli, native_tag="manylinux_2_28_x86_64"
    )
    spec = BundleSpec.build(
        target_key="linux-x86_64",
        cpython_src=_fake_cpython(tmp_path),
        wheel_paths=wheels,
        output_root=tmp_path / "out",
        install_wheels=False,
    )
    p = assemble(spec)
    bundle = p.bundle_dir
    assert (bundle / "python" / "bin" / "python3").exists()
    assert (bundle / "bin" / "decoy").exists()
    assert (bundle / "wheels").is_dir()
    manifest = json.loads((bundle / "bundle-manifest.json").read_text())
    assert manifest["target"] == "linux-x86_64"
    assert manifest["engine_version"] == engine
    assert manifest["native_version"] == engine
    assert manifest["managed_runtime"] is True
    assert manifest["native_abi_expected"] == pins["DECOY_LAUNCH_NATIVE_ABI"]
    # The launcher is executable and sets the managed-runtime marker.
    launcher = (bundle / "bin" / "decoy").read_text()
    assert "DECOY_MANAGED_RUNTIME=1" in launcher
