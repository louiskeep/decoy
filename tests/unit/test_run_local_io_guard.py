"""`_write_mask_outputs` refuses an s3/gcs target on its own.

`decoy run` reaches the writer only after `_load_sources_from_config`, which
already refuses cloud endpoints, so an end-to-end run cannot show whether
the writer's own check is present. A caller that hands the writer a result
directly must still get the typed refusal, and no local target may be
written first: otherwise the loop writes the file targets, skips the cloud
one, and returns as if every output landed.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pytest

from decoy.cli.extras import UnsupportedCloudEndpointError
from decoy.cli.run import _write_mask_outputs


def _config(tmp_path: Path) -> dict:
    return {
        "targets": {
            "local": {"type": "file", "format": "csv", "path": str(tmp_path / "local.csv")},
            "remote": {
                "type": "gcs",
                "format": "csv",
                "bucket": "test-bucket",
                "object": "remote.csv",
            },
        },
    }


def _result() -> SimpleNamespace:
    table = pa.table({"ssn": ["000000000"]})
    return SimpleNamespace(outputs={"local": table, "remote": table})


def test_cloud_target_refused_before_any_write(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedCloudEndpointError, match="gcs target 'remote'"):
        _write_mask_outputs(_config(tmp_path), _result(), tmp_path)
    assert not (tmp_path / "local.csv").exists()


def test_local_only_targets_still_write(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    del cfg["targets"]["remote"]
    _write_mask_outputs(cfg, _result(), tmp_path)
    assert (tmp_path / "local.csv").read_text(encoding="utf-8").splitlines() == [
        "ssn",
        "000000000",
    ]
