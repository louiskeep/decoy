# Contributing to decoy

Thanks for considering a contribution. `decoy` is the CLI front end for [`decoy-engine`](https://github.com/louiskeep/decoy-engine); most data-plane changes belong in the engine repo rather than here.

## Reporting bugs and requesting features

[GitHub Issues](https://github.com/louiskeep/decoy/issues) is the right channel for both. A good bug report includes:

- CLI version (`decoy --version`)
- Engine version (`python -c "import decoy_engine; print(decoy_engine.__version__)"`)
- The exact command you ran
- A minimal `pipeline.yaml` that reproduces the issue (omit any real data)
- The full traceback or `--json` error envelope

For security issues, do not file a public issue: see [`SECURITY.md`](SECURITY.md).

## Local development

```
git clone https://github.com/louiskeep/decoy
cd decoy
python -m venv .venv
source .venv/bin/activate    # PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Tests:

```
pytest tests/unit/
pytest tests/e2e/
```

A green local run on Python 3.10, 3.11, and 3.12 is the bar before requesting review.

## Pull requests

- One topic per PR. Smaller diffs land faster.
- Use `git commit -s` to sign off (Developer Certificate of Origin). The project is licensed under BUSL-1.1, which auto-converts to Apache-2.0 on the Change Date (2030-05-10). Contributions are accepted under the project license.
- User-visible changes (new command, new flag, exit-code semantics, output format) need a `CHANGELOG.md` entry under `[Unreleased]`.
- If a change is more than one PR, file an Issue describing the plan first.

## Code style

`ruff` for lint + format. Run `ruff check src/ tests/` and `ruff format src/ tests/` before pushing.

## Where things live

See [`CODEMAP.md`](CODEMAP.md) for the package layout.
