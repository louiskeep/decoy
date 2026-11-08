"""One run_pipeline cell over a gen.py-style Parquet source; prints one JSON line.

cell=resident_nosink  pq.read_table, no sink (what `decoy run` does today)
cell=resident_sink    pq.read_table, ParquetTransactionalSink
cell=lazy_sink        LazySource(path), ParquetTransactionalSink
Usage: engine_cell.py SOURCE ROWS CELL WORKDIR
"""

import json
import os
import resource
import sys
import time
from pathlib import Path


def status(key: str) -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(key + ":"):
            return int(line.split()[1]) * 1024
    raise RuntimeError(key)


def main() -> None:
    src, rows, cell, work = sys.argv[1], int(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
    os.environ.setdefault("DECOY_MASK_SECRET", "ab" * 32)
    import pyarrow as pa
    import pyarrow.parquet as pq

    from decoy_engine.config import PipelineConfig
    from decoy_engine.execution import run_pipeline
    from decoy_engine.execution._transactional_sink import ParquetTransactionalSink
    from decoy_engine.profile._readers import LazySource

    config = PipelineConfig.model_validate({
        "version": 2,
        "global_settings": {"seed": 42, "mask_secret_ref": "env:DECOY_MASK_SECRET"},
        "sources": {"t": {"type": "file", "format": "parquet", "path": src}},
        "tables": [{"name": "t", "columns": [
            {"name": "email", "strategy": "hash", "namespace": "bench_ns"},
            {"name": "secret", "strategy": "redact"},
            {"name": "zip", "strategy": "truncate", "provider_config": {"length": 3, "keep": "head"}},
            {"name": "ref", "strategy": "passthrough"}]}],
        "targets": {"t": {"type": "file", "format": "parquet", "path": "/dev/null"}},
    }).model_dump()
    work.mkdir(parents=True, exist_ok=True)
    Path("/proc/self/clear_refs").write_text("5")
    floor = status("VmRSS")
    t0 = time.perf_counter()
    source = LazySource(Path(src)) if cell == "lazy_sink" else pq.read_table(src)
    kwargs = {} if cell == "resident_nosink" else {"sink": ParquetTransactionalSink(work / "out")}
    result = run_pipeline(config, sources={"t": source}, engine_version="run-stream-probe", **kwargs)
    if cell == "resident_nosink":
        pq.write_table(result.outputs["t"], work / "out.parquet")
    else:
        from decoy_engine.execution import _isolated_worker
        _isolated_worker._finalize_outputs(result, str(work / "out"))
    wall = time.perf_counter() - t0
    m = result.quality_metrics
    ex = m.get("execution") or {}
    auto = m.get("auto_chunk") or {}
    print(json.dumps({
        "cell": cell, "rows": rows, "wall_s": round(wall, 2),
        "increment_mb": round((status("VmHWM") - floor) / 2**20, 1),
        "lifetime_peak_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "arrow_pool_max_mb": round(pa.default_memory_pool().max_memory() / 2**20, 1),
        "execution_mode": ex.get("execution_mode"),
        "outputs_streamed": ex.get("outputs_streamed"),
        "loaded_fully_in_memory": ex.get("loaded_fully_in_memory"),
        "auto_chunk": {k: auto.get(k) for k in ("mode", "input", "output", "reason")},
        "native_admitted": (m.get("chunked_route") or {}).get("native_admitted"),
    }))


if __name__ == "__main__":
    main()
