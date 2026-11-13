"""CC1: the cloud root rule, the GCS refusal and side files out of `out/` for the cloud kind.

Every case is a config dict (nothing is contacted). `layout_issues` is the one check that
`validate`, `ci check` and `run` share, so the cells run it; AT-C53 also runs the gate itself.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
import yaml
from tests.csv_sources import csv_source

from decoy.cli.gate import run_gate_on_config
from decoy.cli.io import OutputPlacement
from decoy.cli.io._cloud import CloudRoot, cloud_root, new_cloud_run_id
from decoy.cli.io._layout import is_run_id, pipeline_name_for
from decoy.cli.io._placement import layout_issues

SPLIT = "layout.delivery_root_split"
INVALID = "layout.cloud_target_invalid"
UNSUPPORTED = "layout.cloud_target_unsupported"
IN_OUT = "layout.side_file_in_out"
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="symlinks need POSIX here")


def _project(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "decoy.yaml").write_text("kind: decoy-project/v1\n", encoding="utf-8")
    yaml_path = root / "pipelines" / "p.yaml"
    yaml_path.parent.mkdir()
    yaml_path.write_text("name: p\n", encoding="utf-8")
    return root, yaml_path


def _s3(key: str, **fields: object) -> dict:
    return {"type": "s3", "bucket": "b", "region": "us-east-1", "key": key, **fields}


def _targets(**entries: dict) -> dict:
    return {"targets": entries}


def _codes(issues: list) -> list[str]:
    return [err.code for _loc, err in issues]


# --- AT-C04: unsafe keys ---------------------------------------------------------------

BAD_KEYS = [
    "/a",
    "a/",
    "a//b",
    "a/../b",
    "a/./b",
    "a/b\n",
    "a\x01",
    "d/MANIFEST",
    "MANIFEST",
]


@pytest.mark.parametrize("key", BAD_KEYS)
def test_at_c04_an_unsafe_key_is_invalid_and_names_the_table_not_the_key(
    tmp_path: Path, key: str
) -> None:
    _root, yaml_path = _project(tmp_path)
    issues = layout_issues(yaml_path, _targets(tbl=_s3(key)))
    assert _codes(issues) == [INVALID]
    assert "tbl" in issues[0][1].message
    assert "a/" not in issues[0][1].message


@pytest.mark.parametrize("key", ["d/MANIFEST.csv", "d/runsheet.csv", "x.csv", "a/b/c.parquet"])
def test_at_c04_safe_keys_pass(tmp_path: Path, key: str) -> None:
    _root, yaml_path = _project(tmp_path)
    assert layout_issues(yaml_path, _targets(t=_s3(key))) == []


def test_at_c04_two_tables_sharing_a_basename_is_invalid(tmp_path: Path) -> None:
    _root, yaml_path = _project(tmp_path)
    issues = layout_issues(yaml_path, _targets(first=_s3("d/x.csv"), second=_s3("d/x.csv")))
    assert _codes(issues) == [INVALID]
    assert "second" in issues[0][1].message


def test_at_c04_an_implicit_root_without_a_name_uses_the_stem_slug(tmp_path: Path) -> None:
    yaml_path = tmp_path / "orders.yaml"
    yaml_path.write_text("x: 1\n", encoding="utf-8")
    config = _targets(t=_s3("d/x.csv"))
    assert layout_issues(yaml_path, config) == []
    # The one naming rule of local delivery decides the pipeline, so the prefix follows it.
    name = pipeline_name_for(tmp_path, yaml_path, None).name
    root = cloud_root(config, name)
    assert name == "orders" and root is not None and root.prefix == "d/orders"


def test_a_bad_declared_name_is_reported_once_by_the_naming_rule(tmp_path: Path) -> None:
    yaml_path = tmp_path / "p.yaml"
    yaml_path.write_text("x: 1\n", encoding="utf-8")
    config = {**_targets(t=_s3("d/x.csv")), "name": "bad name"}
    assert _codes(layout_issues(yaml_path, config)) == ["layout.pipeline_name_invalid"]


def test_a_broken_project_marker_is_reported_once(tmp_path: Path) -> None:
    (tmp_path / "decoy.yaml").write_text("kind: nope\n", encoding="utf-8")
    yaml_path = tmp_path / "p.yaml"
    yaml_path.write_text("x: 1\n", encoding="utf-8")
    assert _codes(layout_issues(yaml_path, _targets(t=_s3("d/x.csv")))) == [
        "layout.project_marker_invalid"
    ]


# --- AT-C04: split roots ---------------------------------------------------------------


@pytest.mark.parametrize(
    "second",
    [
        {"type": "file", "format": "csv", "path": "b.csv"},
        {"type": "s3", "bucket": "other", "region": "us-east-1", "key": "d/b.csv"},
        {"type": "s3", "bucket": "b", "region": "eu-west-1", "key": "d/b.csv"},
        {"type": "s3", "bucket": "b", "region": "us-east-1", "key": "e/b.csv"},
        {"type": "s3", "bucket": "b", "region": "us-east-1", "key": "b.csv"},
        {"type": "gcs", "bucket": "b", "object": "d/b.csv"},
    ],
    ids=["file", "bucket", "region", "directory", "no-directory", "type"],
)
def test_at_c04_a_split_root_is_refused(tmp_path: Path, second: dict) -> None:
    _root, yaml_path = _project(tmp_path)
    issues = layout_issues(yaml_path, _targets(a=_s3("d/a.csv"), b=second))
    assert SPLIT in _codes(issues)
    message = next(err.message for _loc, err in issues if err.code == SPLIT)
    assert "d/a.csv" not in message


def test_at_c04_the_same_root_is_one_root(tmp_path: Path) -> None:
    _root, yaml_path = _project(tmp_path)
    config = _targets(a=_s3("d/a.csv"), b=_s3("d/b.csv"))
    assert layout_issues(yaml_path, config) == []


# --- AT-C17 and AT-C40: unsupported fields ----------------------------------------------


@pytest.mark.parametrize(
    ("config", "placement", "field"),
    [
        (_targets(tbl=_s3("d/a.csv", credentials_ref="r1")), OutputPlacement(), "credentials_ref"),
        (
            _targets(tbl=_s3("d/a.csv", endpoint_url="http://host.invalid:9000")),
            OutputPlacement(),
            "endpoint_url",
        ),
        (
            {**_targets(tbl=_s3("d/a.csv")), "quarantine": {"enabled": True}},
            OutputPlacement(),
            "quarantine.enabled",
        ),
        (_targets(tbl=_s3("d/a.csv")), OutputPlacement(chunked=True), "--chunked"),
        (
            _targets(tbl={"type": "gcs", "bucket": "b", "object": "d/a.csv"}),
            OutputPlacement(),
            "type",
        ),
    ],
    ids=["credentials_ref", "endpoint_url", "quarantine", "chunked", "gcs"],
)
def test_at_c17_at_c40_each_unsupported_field_alone_is_refused_naming_it(
    tmp_path: Path, config: dict, placement: OutputPlacement, field: str
) -> None:
    _root, yaml_path = _project(tmp_path)
    issues = layout_issues(yaml_path, config, placement)
    assert _codes(issues) == [UNSUPPORTED]
    message = issues[0][1].message
    assert field in message and "tbl" in message
    assert "host.invalid" not in message and "r1" not in message


def test_at_c17_endpoint_url_on_a_source_passes_the_rule(tmp_path: Path) -> None:
    _root, yaml_path = _project(tmp_path)
    config = {
        "sources": {"s": {**_s3("in.csv"), "endpoint_url": "http://host.invalid:9000"}},
        **_targets(t=_s3("d/a.csv")),
    }
    assert layout_issues(yaml_path, config) == []


def test_at_c17_a_file_only_config_is_untouched_by_the_cloud_rule(tmp_path: Path) -> None:
    _root, yaml_path = _project(tmp_path)
    config = _targets(t={"type": "file", "format": "csv", "path": "a.csv"})
    assert layout_issues(yaml_path, config, OutputPlacement(chunked=True)) == []


# --- AT-C35 and AT-C36a ------------------------------------------------------------------


def test_at_c35_a_cloud_run_id_is_a_run_id_with_all_32_hex_digits() -> None:
    started = datetime(2026, 11, 12, 10, 30, 0, 123456, tzinfo=timezone.utc)
    invocation = "0123456789abcdef0123456789abcdef"
    run_id = new_cloud_run_id(started, invocation)
    assert is_run_id(run_id)
    assert run_id.partition("-")[2] == invocation


def test_at_c36a_two_pipelines_under_one_directory_have_two_roots() -> None:
    config = _targets(t=_s3("exports/a.csv"))
    dev, stg = cloud_root(config, "dev"), cloud_root(config, "stg")
    assert isinstance(dev, CloudRoot) and isinstance(stg, CloudRoot)
    assert (dev.prefix, stg.prefix) == ("exports/dev", "exports/stg")
    assert dev.pointer_key == "exports/dev/CURRENT"
    assert stg.pointer_key == "exports/stg/CURRENT"
    bare = cloud_root(_targets(t=_s3("a.csv")), "dev")
    assert bare is not None and bare.prefix == "dev"
    assert cloud_root(_targets(t={"type": "file", "path": "a.csv"}), "dev") is None


# --- AT-C53: side files and the cloud lock folder ---------------------------------------


@pytest.mark.parametrize("flag", ["--evidence-out", "--vault"])
@pytest.mark.parametrize("rel", ["out/p/x", "out/x"])
def test_at_c53_a_side_file_under_out_is_refused_on_the_cloud_kind(
    tmp_path: Path, flag: str, rel: str
) -> None:
    root, yaml_path = _project(tmp_path)
    placement = OutputPlacement(typed=((flag, root / rel),))
    issues = layout_issues(yaml_path, _targets(t=_s3("d/a.csv")), placement)
    assert _codes(issues) == [IN_OUT]
    assert flag in issues[0][1].message and str(tmp_path) not in issues[0][1].message
    assert not (root / "out").exists()


@pytest.mark.parametrize("flag", ["--evidence-out", "--vault"])
def test_at_c53_the_implicit_project_root_holds_the_lock_folder_too(
    tmp_path: Path, flag: str
) -> None:
    yaml_path = tmp_path / "p.yaml"
    yaml_path.write_text("x: 1\n", encoding="utf-8")
    config = {**_targets(t=_s3("d/a.csv")), "name": "orders"}
    inside = OutputPlacement(typed=((flag, tmp_path / "out" / "orders" / "x"),))
    assert _codes(layout_issues(yaml_path, config, inside)) == [IN_OUT]


@posix_only
def test_at_c53_a_symlink_alias_of_out_is_refused(tmp_path: Path) -> None:
    root, yaml_path = _project(tmp_path)
    (root / "out" / "p").mkdir(parents=True)
    (root / "alias").symlink_to(root / "out" / "p")
    placement = OutputPlacement(typed=(("--vault", root / "alias" / "v.db"),))
    assert _codes(layout_issues(yaml_path, _targets(t=_s3("d/a.csv")), placement)) == [IN_OUT]


def test_at_c53_a_typed_out_dir_does_not_hide_the_cloud_lock_folder(tmp_path: Path) -> None:
    root, yaml_path = _project(tmp_path)
    placement = OutputPlacement.fixed(tmp_path / "build", (("--vault", root / "out" / "p" / "v"),))
    assert _codes(layout_issues(yaml_path, _targets(t=_s3("d/a.csv")), placement)) == [IN_OUT]


def test_at_c53_a_side_file_outside_out_passes(tmp_path: Path) -> None:
    root, yaml_path = _project(tmp_path)
    typed = (("--vault", root / "v.db"), ("--evidence-out", tmp_path / "e.json"))
    placement = OutputPlacement(typed=typed)
    assert layout_issues(yaml_path, _targets(t=_s3("d/a.csv")), placement) == []


def test_at_c53_the_gate_reports_the_refusal_and_the_cloud_rule(tmp_path: Path) -> None:
    root, _ = _project(tmp_path)
    src = tmp_path / "in.csv"
    pd.DataFrame({"email": ["a@b.com"]}).to_csv(src, index=False)
    cfg = {
        "version": 2,
        "name": "p",
        "global_settings": {"seed": 42},
        "sources": {"customers": csv_source(src)},
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {
                        "name": "email",
                        "strategy": "faker",
                        "provider": "person_email",
                        "deterministic": True,
                        "namespace": "cust_ns",
                    }
                ],
            }
        ],
        "targets": {"customers": _s3("d/a.csv", format="csv")},
    }
    path = root / "pipelines" / "p.yaml"
    path.write_text(yaml.dump(cfg), encoding="utf-8")
    placement = OutputPlacement(typed=(("--vault", root / "out" / "v.db"),))
    result = run_gate_on_config(cfg, path, placement=placement)
    assert [f.code for f in result.findings] == [IN_OUT]
    cfg["targets"]["customers"] = _s3("d/MANIFEST", format="csv")
    bad = run_gate_on_config(cfg, path)
    assert [f.code for f in bad.findings] == [INVALID]
