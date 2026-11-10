"""Seeded row-position selection, the one rule for "a random sample of N rows".

`decoy scan --sample random`, the `decoy.scan` API and `decoy fit --rows` all draw their rows
here. The positions are exactly the ones `DataFrame.sample(n=k, random_state=seed)` picks, so a
saved sample does not change when a caller moves onto this module. Positions are chosen from the
row count alone, before any cell is read, so a caller that holds only a count (a file too large
to load) can still pick rows and then read just those.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    import pandas as pd


def sample_positions(n_total: int, k: int, seed: int, *, keep_order: bool = False) -> np.ndarray:
    """Return `k` distinct row positions out of `n_total`, drawn with a fixed `seed`.

    Default order is the draw order, the order `DataFrame.sample` returns rows in.
    `keep_order=True` returns the positions ascending, so rows stay in file order.
    """
    import numpy as np

    if not 0 <= k <= n_total:
        raise ValueError(f"cannot pick {k} rows out of {n_total}.")
    positions = np.random.RandomState(seed).choice(n_total, size=k, replace=False)
    positions = positions.astype(np.intp)
    return np.sort(positions) if keep_order else positions


def sample_frame(df: pd.DataFrame, k: int, seed: int) -> pd.DataFrame:
    """Return `k` randomly chosen rows of `df` (draw order) with a fresh 0..k-1 index."""
    return df.iloc[sample_positions(len(df), k, seed)].reset_index(drop=True)
