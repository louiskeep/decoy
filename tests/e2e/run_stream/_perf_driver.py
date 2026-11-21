"""One `decoy run` in its own process, lazy or resident, for the VM peak-RSS and timing cells.

Usage: python _perf_driver.py CONFIG lazy|base. Prints one JSON line: exit code, wall seconds
and the process peak RSS (the OS unit: KiB on Linux, bytes on macOS; both modes use the same).
"""

from __future__ import annotations

import json
import resource
import sys
import time

from typer.testing import CliRunner

from decoy.__main__ import app


def main() -> None:
    config, mode = sys.argv[1], sys.argv[2]
    if mode == "base":
        import decoy.cli.run._execute as execute

        execute.lazy_sources = lambda config_dict, base_dir: {}
    start = time.perf_counter()
    result = CliRunner().invoke(app, ["run", config])
    seconds = time.perf_counter() - start
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(json.dumps({"exit": result.exit_code, "seconds": seconds, "peak_rss": peak}))


if __name__ == "__main__":
    main()
