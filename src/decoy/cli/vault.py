"""`vault` -- retired command group (CLI redesign).

S4b (D5) relocated the sole `vault info` command to `decoy report vault`
(`decoy.cli.report._vault`), folding vault inspection into the single post-run
`report` noun. The `vault` sub-app no longer exists.

A vault file is an AES-GCM-encrypted map from (namespace, masked_value) to the
original source value, written by `decoy run --vault` for columns declared
`vault: true`; `decoy report vault` inspects one without decoding every entry.

This module is intentionally empty: it registers no Typer sub-app and exports
nothing.
"""

from __future__ import annotations
