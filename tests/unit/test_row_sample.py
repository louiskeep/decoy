"""`decoy._row_sample`: the one seeded row-position rule shared by scan, the API and fit."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from decoy._row_sample import sample_frame, sample_positions

# Fixed n, k and seed give this exact list. A change here moves every saved random sample.
GOLDEN_DRAW_ORDER = [0, 17, 15, 1, 8]


def test_golden_positions_draw_order_and_file_order() -> None:
    assert sample_positions(20, 5, 42).tolist() == GOLDEN_DRAW_ORDER
    assert sample_positions(20, 5, 42, keep_order=True).tolist() == sorted(GOLDEN_DRAW_ORDER)


@pytest.mark.parametrize("n_total,k", [(10, 10), (10, 1), (1000, 37), (5000, 4999), (7, 0)])
def test_positions_match_dataframe_sample(n_total: int, k: int) -> None:
    df = pd.DataFrame({"v": range(n_total)})
    expected = df.sample(n=k, random_state=42).index.to_numpy()
    assert np.array_equal(sample_positions(n_total, k, 42), expected)
    pd.testing.assert_frame_equal(
        sample_frame(df, k, 42), df.sample(n=k, random_state=42).reset_index(drop=True)
    )


def test_positions_are_distinct_in_range_and_repeatable() -> None:
    got = sample_positions(1000, 300, 7)
    assert len(set(got.tolist())) == 300
    assert got.min() >= 0 and got.max() < 1000
    assert np.array_equal(got, sample_positions(1000, 300, 7))
    assert not np.array_equal(got, sample_positions(1000, 300, 8))


def test_more_rows_than_exist_is_refused() -> None:
    with pytest.raises(ValueError):
        sample_positions(5, 6, 42)
