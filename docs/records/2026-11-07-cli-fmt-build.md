# CLI-FMT Part A build record

Status: record

## Environment

Base `05bf840`. VM venv `venv-cli-vmrun-1` from `requirements-dev.lock`, Python 3.10.22, `decoy-engine==0.19.0`, pytest 9.2.0, ruff 0.15.14. Mac: `venv-cli-mac`, macOS arm64, run with `PYTHONPATH=src` because the venv is editable against another worktree.

## Write sites

W1 to W5 and the chunked writer are as measured in the handoff. All table writes now live in `src/decoy/cli/io/_targets.py`. Out of scope and unchanged: the `api.py` source spool, the vault file, evidence and report output, the demo sample CSVs, `decoy subset`, the DuckDB snapshot.

## No lossless Arrow mapper

It changes behavior only for an int column holding a null, and `write_fixed_width` refuses a null in every column type, so the write fails closed either way. An int64 column without nulls stays int64 through `to_pandas()`.

## Red on base (tests only, `src` stashed)

`tests/e2e/cli_fmt`: 27 failed, 6 passed. The 6 that pass on base keep behavior: csv at `.csv`, `.txt`, `.csv.gz`, csv-bytes pin, parquet at `.parquet` and `.PARQUET`. Failing assertions: file bytes are CSV where `PAR1` or fixed width is expected; exit 0 or 3 where 1 is expected for each mismatch and chunked refusal; `DID NOT RAISE` for `mask()`. `tests/unit/cli_fmt` fails at import (`decoy.cli.io` absent), a collection error, not an assertion.

## Green

`pytest tests/e2e/cli_fmt tests/unit/cli_fmt`: 62 passed on the VM, then 63 after AT-F7 gained the demo hash pin (`d784565e...`, measured on base, stable across two runs).

## Mutations (head `a83223e`)

Each turns a named test red: suffix-keyed writer, dropped contradiction check, exit tuple, dropped chunked branch, dropped archive branch, dropped `.pq`, final-suffix-only compression, dropped `empty_schema`, header per chunk, check removed from `_load_sources_from_config`, local resolver in demo, unmask `to_csv`, dropped int coercion, leading zeros, `re.match` with `$`, override keeps declared format, override keeps layout, path in message, `format_for_path` always csv.

Survivors: dropping the int64 range check (the Int64 build raises OverflowError, exit 3, no file, value-free, so the outcome is the same) and routing the detokenize pandas Parquet write through `pa.Table` (the bytes are identical).

## Gates

VM `gates.sh --keep-going --baseline`: ruff pass, tests pass (447). Sentry: one branch-only failure, `test_cli_reference_is_up_to_date`, caused by the generated reference being edited while the run was in flight; the three surface tests pass on a rerun. mypy is not installed on the VM; mypy on the devbox shows no error in the touched new module.
macOS arm64: named, behavior-kept, `git grep` files and `tests/sentry`: 904 passed, 4 skipped, 1 xfailed (the strict xfail), no failure outside the surface test above, which passes with `PYTHONPATH=src`.

## Size

See `git diff --shortstat origin/main...HEAD`: hand-written insertions exceed the 900 line STOP in the handoff (tests about 600, `_targets.py` 358).

## V2-LOG

`FixedWidthWriteError` text names the local path; CSV and Parquet write in place; `--duckdb-source` and `data=` stage before the target check; `run.py` over 900 lines; pandas 3 `StringDtype` in the canonical-int rule.
