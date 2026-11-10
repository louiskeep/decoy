"""`decoy scan` internals: argument resolution, the engine call and the report.

Other packages import these names, never `decoy.cli.scanning._multi`.
"""

from decoy.cli.scanning._multi import ScanUsageError, run_scan, table_name_from_path

__all__ = ["ScanUsageError", "run_scan", "table_name_from_path"]
