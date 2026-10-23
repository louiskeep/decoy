"""`decoy storm` -- retired command group (CLI redesign).

S3a merged the former `storm analyze` (pre-run profiling) and its saved-scan
subcommands (`fields`/`show`/`diff`) into the top-level `decoy scan` verb (see
`decoy.cli.scan`). S4b then relocated the lone post-run `integrity` command
to `decoy report integrity` (`decoy.cli.report._integrity`), so the `storm`
group no longer exists.

This module is intentionally empty: it registers no Typer sub-app and exports
nothing. `decoy scan` owns pre-run profiling; `decoy report integrity` owns
post-mask verification. The STORM progress animation lives in
`decoy.ui.storm_animation`, which `decoy.cli.scan` imports directly.
"""

from __future__ import annotations
