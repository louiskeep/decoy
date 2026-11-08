# CLI-MAC-TESTS S2 build record

Status: record (2026-11-08)

Slice S2 of `docs/plans/2026-11-08-cli-mac-tests.md`: one soft-wrapped stderr console and the
"one stderr console" sentry. Branch `feat/cli-mac-tests-s2`, base CLI `origin/main` `92cdcac`
(includes #109). Engine pin `4a0d5b1f`.

## STEP ZERO

- `Console(` is constructed once in `src/` (`ui/output.py`). No `rich.print(..., file=)`, no
  `soft_wrap=False`, no `Panel`/`Table` passed to `err_console.print`.
- No test matches stderr across a newline. Line-based readers are `test_run_otel.py:136`
  (one warning line, soft wrap only lowers the count) and `test_run_validate_always.py:241`
  (flattens whitespace).
- The nine #109 `soft_wrap=True` sites in `run.py` (`:223 :530 :1118 :1121 :1130 :1132 :1171
  :1726 :1735`) and the wrap comment are removed. `markup=False` and notify code stay.
- Review found a class the plan missed: five `err_console.print_exception()` sites (`run.py`,
  `scan.py`, `report.py`, `subset.py`, `demo.py`). A soft-wrapped traceback crops each frame
  header at the panel edge, so they now go through `ui.output.print_traceback`, which prints
  `Traceback()` with `soft_wrap=False`. The sentry exempts that helper by exact
  (file, function) and forbids `err_console.print_exception(` elsewhere (shape e).

## Acceptance tests

| AT | Test | Red on base | Green |
|---|---|---|---|
| 6 | `test_output_modes.py` 3 human cells, 2 JSON cells | compile cells red on `92cdcac` (VM). The `run` cell is base-green because #109 already soft-wraps `run`. JSON cells green by design. | VM, Mac |
| 7 | `tests/sentry/test_one_stderr_console.py` | file absent | VM, Mac |
| 8 | `test_plan_command.py::test_with_invalid_profile_json`, `test_a_long_path_in_run_error_text_is_printed_whole` (now `COLUMNS=80`) | id 8 red on the Mac at `92cdcac` | VM, Mac |
| traceback | `test_verbose_traceback_keeps_frame_locations_under_a_long_directory` | red at `ff9bc0c` (VM: `eng_frame.py:2 in go` count 0, expected 1) | VM |

Mac `decoy.__file__`: `/Users/camkeep/decoy/cli-mac-s2/src/decoy/__init__.py`.

## Mutations (each reverted, never committed)

| # | Mutation | Head | Red |
|---|---|---|---|
| 6 | `soft_wrap=False` in `_make_console` | `ff9bc0c` | VM: 3 human AT-6 cells and both long-path tests in `test_run_validate_always.py`. Mac: those plus id 8. |
| 7a-d | seeded in `cli/demo.py`: aliased `Console`, `rich.print(file=)`, `soft_wrap=False` on `err_console.print`, `err_console.print(Panel())` | `ff9bc0c` | `test_src_has_one_soft_wrapped_stderr_console` with `(a)` to `(d)` |
| 7e | seeded `err_console.print_exception()` in `cli/demo.py` | `e12d4f8` | same test, `(e)` |
| 8 | `Traceback(), soft_wrap=True` in `print_traceback` | `e12d4f8` | traceback cell red on the VM |

The sentry also self-tests each shape (`SEEDED`), the helper exemption, and a nested import
that must not hide a module-level `Console` alias.

## Tests run

VM T1 (`vm-run cli`, head `e12d4f8`, 712 passed): `tests/sentry`, `test_output_modes`, `test_run_validate_always`,
`test_run_notify`, `test_plan_command`, `test_run_otel`, `test_mask_secret_single_read`,
`tests/unit/test_cli_surface.py`, and the demo, scan, subset and report command tests.
The full suite (AT-9) is run by the orchestrator on the final head.
