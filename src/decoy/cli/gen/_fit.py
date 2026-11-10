"""The exact-mode fit behind `decoy fit` and `decoy init <csv> --preset generate`.

One function reads the CSV (whole, or a seeded sample spread across it when it is over the row
limit) and builds the `distribution-snapshot/v1` document, so both commands fit identically.
`read_fit_csv` is the one `pandas.read_csv` call of the fit path; the DP mode in `cli/fit.py`
reads through it too.
"""

from __future__ import annotations

import contextlib
import csv
import io
import warnings
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from decoy._row_sample import sample_positions

# Fixed so the same file always gives the same sample. Part of the documented behavior: change
# it and every sampled fit changes.
FIT_SAMPLE_SEED = 42
_COUNT_CHUNK = 100_000


class FitSourceError(Exception):
    """The source cannot be fitted. `message` names files and columns, never a cell value."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class ExactFit:
    snapshot: dict[str, Any]
    rows_used: int
    rows_total: int


def read_fit_csv(source: Any, **kwargs: Any) -> Any:
    """The one CSV read of the fit path: a caller-named file with its own parse flags."""
    import pandas as pd

    return pd.read_csv(source, **kwargs)


@contextlib.contextmanager
def strict_csv() -> Iterator[None]:
    """Turn pandas' ParserWarning into an error for the reads inside.

    With `index_col=False`, pandas drops the extra fields of an over-wide first record and only
    warns; as an error the read fails and fit refuses the file instead of fitting cut rows.
    """
    import pandas as pd

    with warnings.catch_warnings():
        warnings.simplefilter("error", pd.errors.ParserWarning)
        yield


def fit_exact_snapshot(
    source: Path,
    *,
    row_limit: int,
    parse_dates: Sequence[str] = (),
    joint_pairs: Sequence[tuple[str, str]] | None = None,
    include_values: bool = False,
) -> ExactFit:
    """Fit the exact (non-DP) snapshot of `source`. Raises `FitSourceError`."""
    import numpy as np
    from decoy_engine import distribution_snapshot_document

    def unreadable() -> FitSourceError:
        # No str(exc): a pandas parse error can quote a source cell.
        return FitSourceError(f"could not read {source} as a CSV.")

    # Every read uses `index_col=False`: with pandas' default, a record wider than the header
    # silently turns the first column into the index and shifts every value one column left.
    # With False, pandas raises on a wide record or, for the first one, drops the extra fields
    # with a ParserWarning; `strict_csv` makes that warning an error, so an over-wide record is
    # always refused instead of fitted.
    # A file over the limit is sampled by record position BEFORE pandas infers types, so a row
    # outside the sample cannot change a column's kind and the file is never fully loaded.
    # Both passes below read the file through pandas' own record rule (blank lines skipped,
    # quoted newlines inside one record), so a position means the same record in each. The
    # sampled records are then parsed by the one read below, exactly as if they were the file.
    rows_total = 0
    kept: Any = None
    seen = 0
    kept_rows: list[list[Any]] = []
    sample_header: list[Any] = []
    read_failed = False
    for phase in ("count", "select"):
        if phase == "select":
            if rows_total <= row_limit:
                break
            kept = sample_positions(rows_total, row_limit, FIT_SAMPLE_SEED, keep_order=True)
            seen = 0
        try:
            with strict_csv():
                for chunk in read_fit_csv(
                    source,
                    chunksize=_COUNT_CHUNK,
                    dtype=str,
                    index_col=False,
                    usecols=[0] if phase == "count" else None,
                    # Literal text, so the parse below sees what the file holds.
                    na_filter=phase == "count",
                ):
                    if kept is None:
                        rows_total += len(chunk)
                        continue
                    lo, hi = np.searchsorted(kept, [seen, seen + len(chunk)])
                    sample_header = list(chunk.columns)
                    picked = chunk.iloc[kept[lo:hi] - seen]
                    kept_rows.extend(picked.fillna("").to_numpy().tolist())
                    seen += len(chunk)
        except Exception:
            read_failed = True
        if read_failed:
            raise unreadable()
    read_target: Any = source
    if kept is not None:
        if seen != rows_total:
            raise FitSourceError(
                "the CSV changed while it was being read; run the command again.",
                "fit_source_changed",
            )
        # The sampled records as CSV text, parsed below exactly as if they were the file.
        sample_text = io.StringIO()
        sample_writer = csv.writer(sample_text, lineterminator="\n")
        sample_writer.writerow(sample_header)
        sample_writer.writerows(kept_rows)
        sample_text.seek(0)
        read_target = sample_text
    read_failed = False
    try:
        with strict_csv():
            df = read_fit_csv(read_target, parse_dates=list(parse_dates) or False, index_col=False)
    except Exception:
        read_failed = True
    if read_failed:
        raise unreadable()

    missing = [c for c in parse_dates if c not in df.columns]
    if missing:
        raise FitSourceError(f"--parse-dates column(s) not in the CSV: {', '.join(missing)}.")

    # Detection and the snapshot see exactly the rows read above.
    # No profile_row_cap: it profiles head rows only, and a sensitive column can start late.
    snapshot = distribution_snapshot_document(
        df,
        source_label=source.name,
        include_values=include_values,
        joint_columns=list(joint_pairs) if joint_pairs else None,
    )
    return ExactFit(snapshot, rows_used=len(df), rows_total=rows_total or len(df))
