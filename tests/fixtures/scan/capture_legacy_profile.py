"""Regenerate `legacy_profile.json`, the bare `profile.to_dict()` that `decoy scan --output`
wrote before `scan-set/v1`.

Run `python tests/fixtures/scan/capture_legacy_profile.py > tests/fixtures/scan/legacy_profile.json`
on an install of the engine the CLI pins. The call is the one the old `decoy scan` made:
`profile_columns(frame, source_label=<file name>, sample_strategy="head", sample_row_cap=10000)`
then `.to_dict()`. Every name cell holds the canary `ZQCANARY...`, so a test can prove no
reader prints a `top_values` entry.
"""

from __future__ import annotations

import json

import pandas as pd
from decoy_engine import profile_columns

frame = pd.DataFrame(
    {
        "customer_id": ["C1", "C2", "C3", "C4", "C5"],
        "first_name": [f"ZQCANARY{n}" for n in range(5)],
        "email": [f"zqcanary{n}@example.com" for n in range(5)],
        "ssn": ["111-22-3333", "222-33-4444", "333-44-5555", "444-55-6666", "555-66-7777"],
    }
)
profile = profile_columns(
    frame, source_label="people.csv", sample_strategy="head", sample_row_cap=10_000
)
print(json.dumps(profile.to_dict(), indent=2))
