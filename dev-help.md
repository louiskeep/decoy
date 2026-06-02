# CLI Developer Help

Short notes for working in the `decoy` CLI repo.

## Build and test

    pip install -e .
    pytest

The CLI imports `decoy-engine` as a sibling package during local dev. For a fresh-install smoke check, see [docs/release/fresh-install-smoke.md](docs/release/fresh-install-smoke.md).

## Common tasks

- Add a command: drop a module under `src/decoy/cli/`, register it in `src/decoy/__main__.py`, and add a CliRunner test under `tests/`.
- Touch data behavior: do it in `decoy-engine`, not here.
- Edit output formatting: use the Rich helpers in `src/decoy/ui/`; avoid raw `print()` in command bodies.
- Add an example: prefer graph-mode YAML under `examples/`.

## Where to look

See [CODEMAP.md](CODEMAP.md) for the directory map and the "Where Do I Find" pointer table.

---

Full CLI dev-help guide lives in the commercial platform repo.
