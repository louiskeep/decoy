"""End-to-end tests for `decoy fit` + the statistical generate path (WS3).

`decoy fit` wraps the engine's `compute_distribution_snapshot`: it turns
a source CSV into the distribution-snapshot/v1 JSON artifact that
`type: statistical` generate columns consume. The flagship cell runs the
full loop: fit -> validate -> run -> synthetic output shaped like the
source.

The `TestFitDp*` classes below cover the DPS-CLI rewire
(docs/plans/2026-07-24-dps-cli-fit-rewire.md): `--epsilon` now selects a
second mode that calls the engine's `fit_dp_snapshot` (typed-carrier
`dps-marginal/v3`) instead of the removed `apply_dp_noise`. This dev
environment is not a certified DP proof stack (that certification is a
separate, gated follow-up item), so every test that reaches the real
engine call asserts the `dp_stack_uncertified` refusal rather than a
completed release; everything upstream of that call -- mode selection,
declaration parsing, the flag grammar, the omission check -- is exercised
directly against the CLI's own logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from decoy.cli.fit import _build_typed_frame, _map_flag_token

runner = CliRunner()


def _dp_source_csv(tmp_path: Path) -> Path:
    """A source CSV with one column of each carrier kind, plus one
    undeclared column (`notes`) for the omission tests. `is_active` carries
    the raw CSV strings a real export would produce: canonical tokens,
    mixed case, surrounding whitespace, and tokens outside the fixed
    true/false/1/0 grammar."""
    src = tmp_path / "dp_source.csv"
    pd.DataFrame(
        {
            "amount": [10.5, 22.1, 9.9, 100.0, 55.2, 31.4, 18.8, 42.0] * 5,
            "state": (["CA"] * 5 + ["NY"] * 2 + ["TX"]) * 5,
            "is_active": ["True", "false", "1", "0", " TRUE ", "yes", "", "FaLsE"] * 5,
            "notes": ["free text"] * 40,
        }
    ).to_csv(src, index=False)
    return src


def _source_csv(tmp_path: Path) -> Path:
    src = tmp_path / "source.csv"
    pd.DataFrame(
        {
            "amount": [10.5, 22.1, 9.9, 100.0, 55.2, 31.4, 18.8, 42.0] * 25,
            "state": (["CA"] * 5 + ["NY"] * 2 + ["TX"]) * 25,
            "joined": ["2024-01-05", "2024-03-02", "2025-06-01", "2023-12-25"] * 50,
        }
    ).to_csv(src, index=False)
    return src


class TestFit:
    def test_fit_writes_snapshot(self, tmp_path: Path) -> None:
        src = _source_csv(tmp_path)
        out = tmp_path / "snapshot.json"
        result = runner.invoke(app, ["fit", str(src), "--output", str(out)])
        assert result.exit_code == 0, result.output
        snap = json.loads(out.read_text(encoding="utf-8"))
        assert snap["schema_version"] == "distribution-snapshot/v1"
        assert snap["columns"]["amount"]["kind"] == "numeric"
        assert snap["columns"]["state"]["kind"] == "categorical"

    def test_parse_dates_flag(self, tmp_path: Path) -> None:
        src = _source_csv(tmp_path)
        out = tmp_path / "snapshot.json"
        result = runner.invoke(
            app, ["fit", str(src), "--output", str(out), "--parse-dates", "joined"]
        )
        assert result.exit_code == 0, result.output
        snap = json.loads(out.read_text(encoding="utf-8"))
        assert snap["columns"]["joined"]["kind"] == "datetime"

    def test_joint_flag_captures_contingency(self, tmp_path: Path) -> None:
        src = _source_csv(tmp_path)
        out = tmp_path / "snapshot.json"
        result = runner.invoke(
            app, ["fit", str(src), "--output", str(out), "--joint", "state,joined"]
        )
        assert result.exit_code == 0, result.output
        snap = json.loads(out.read_text(encoding="utf-8"))
        assert len(snap["joints"]) == 1
        assert snap["joints"][0]["columns"] == sorted(["state", "joined"])

    def test_bad_joint_spec_exits_usage(self, tmp_path: Path) -> None:
        src = _source_csv(tmp_path)
        result = runner.invoke(
            app,
            [
                "fit",
                str(src),
                "--output",
                str(tmp_path / "s.json"),
                "--joint",
                "only_one",
            ],
        )
        assert result.exit_code == EXIT_USAGE

    def test_default_output_path(self, tmp_path: Path) -> None:
        src = _source_csv(tmp_path)
        result = runner.invoke(app, ["fit", str(src)])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "source.snapshot.json").exists()


class TestFitDpModeSelectionFailClosed:
    """D0: `--epsilon` is the only DP-mode selector. Every DP-only option is
    a usage error without it (else it would silently fall through to the
    exact, non-DP snapshot), and `--epsilon` itself requires --delta plus a
    carrier declaration."""

    def test_delta_without_epsilon_exits_usage(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        result = runner.invoke(app, ["fit", str(src), "--delta", "1e-6"])
        assert result.exit_code == EXIT_USAGE
        assert "dp_mode_not_selected" in result.output
        assert "--delta" in result.output

    def test_dp_number_without_epsilon_exits_usage(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        result = runner.invoke(app, ["fit", str(src), "--dp-number", "amount:0:200"])
        assert result.exit_code == EXIT_USAGE
        assert "dp_mode_not_selected" in result.output

    def test_dp_flag_without_epsilon_exits_usage(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        result = runner.invoke(app, ["fit", str(src), "--dp-flag", "is_active"])
        assert result.exit_code == EXIT_USAGE
        assert "dp_mode_not_selected" in result.output

    def test_dp_text_without_epsilon_exits_usage(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        result = runner.invoke(app, ["fit", str(src), "--dp-text", "state"])
        assert result.exit_code == EXIT_USAGE
        assert "dp_mode_not_selected" in result.output

    def test_numeric_bins_without_epsilon_exits_usage(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        result = runner.invoke(app, ["fit", str(src), "--numeric-bins", "5"])
        assert result.exit_code == EXIT_USAGE
        assert "dp_mode_not_selected" in result.output
        assert "--numeric-bins" in result.output

    def test_allow_omit_without_epsilon_exits_usage(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        result = runner.invoke(app, ["fit", str(src), "--dp-allow-omit"])
        assert result.exit_code == EXIT_USAGE
        assert "dp_mode_not_selected" in result.output
        assert "--dp-allow-omit" in result.output

    def test_epsilon_without_delta_exits_usage(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        result = runner.invoke(
            app, ["fit", str(src), "--epsilon", "1.0", "--dp-number", "amount:0:200"]
        )
        assert result.exit_code == EXIT_USAGE
        assert "dp_mode_delta_required" in result.output

    def test_epsilon_without_carriers_exits_usage(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        result = runner.invoke(app, ["fit", str(src), "--epsilon", "1.0", "--delta", "1e-6"])
        assert result.exit_code == EXIT_USAGE
        assert "dp_mode_no_carriers" in result.output

    def test_epsilon_with_joint_exits_usage_before_csv_read(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        out = tmp_path / "snapshot.json"
        result = runner.invoke(
            app,
            [
                "fit",
                str(src),
                "--output",
                str(out),
                "--epsilon",
                "1.0",
                "--delta",
                "1e-6",
                "--dp-number",
                "amount:0:200",
                "--joint",
                "state,is_active",
            ],
        )
        assert result.exit_code == EXIT_USAGE
        assert "dp_mode_joint_unsupported" in result.output
        assert not out.exists()

    def test_epsilon_with_parse_dates_exits_usage_before_csv_read(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        out = tmp_path / "snapshot.json"
        result = runner.invoke(
            app,
            [
                "fit",
                str(src),
                "--output",
                str(out),
                "--epsilon",
                "1.0",
                "--delta",
                "1e-6",
                "--dp-number",
                "amount:0:200",
                "--parse-dates",
                "state",
            ],
        )
        assert result.exit_code == EXIT_USAGE
        assert "dp_mode_parse_dates_unsupported" in result.output
        assert not out.exists()


class TestFitDpDeclarationValidation:
    """D1: carrier declarations are parsed and validated before the CSV is
    read; a bad spec, a reversed/non-finite domain, or a duplicate/
    conflicting declaration for one column is a usage error, never a
    last-wins overwrite."""

    def _invoke(self, src: Path, *extra: str) -> object:
        return runner.invoke(
            app,
            ["fit", str(src), "--epsilon", "1.0", "--delta", "1e-6", *extra],
        )

    def test_dp_number_missing_parts_exits_usage(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        result = self._invoke(src, "--dp-number", "amount:0")
        assert result.exit_code == EXIT_USAGE
        assert "dp_number_spec_invalid" in result.output

    def test_dp_number_non_numeric_bound_exits_usage(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        result = self._invoke(src, "--dp-number", "amount:zero:200")
        assert result.exit_code == EXIT_USAGE
        assert "dp_number_spec_invalid" in result.output

    def test_dp_number_reversed_domain_exits_usage(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        result = self._invoke(src, "--dp-number", "amount:200:0")
        assert result.exit_code == EXIT_USAGE
        assert "dp_numeric_domain_invalid" in result.output

    def test_dp_number_non_finite_domain_exits_usage(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        result = self._invoke(src, "--dp-number", "amount:0:inf")
        assert result.exit_code == EXIT_USAGE
        assert "dp_numeric_domain_invalid" in result.output

    def test_duplicate_dp_number_declaration_exits_usage(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        result = self._invoke(src, "--dp-number", "amount:0:200", "--dp-number", "amount:0:50")
        assert result.exit_code == EXIT_USAGE
        assert "dp_schema_duplicate_column" in result.output

    def test_conflicting_carrier_declaration_exits_usage(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        result = self._invoke(src, "--dp-number", "state:0:200", "--dp-text", "state")
        assert result.exit_code == EXIT_USAGE
        assert "dp_schema_duplicate_column" in result.output


class TestFitDpFlagGrammar:
    """D6: the flag map is a fixed, case-insensitive, whitespace-trimmed
    true/false/1/0 grammar applied at the CLI seam. Every other token maps
    to null SILENTLY -- no error, warning, or count may be a function of a
    cell's content, and adding a row must not change how any prior cell is
    interpreted (boxing-invariance at this seam)."""

    @pytest.mark.parametrize(
        ("token", "expected"),
        [
            ("true", True),
            ("TRUE", True),
            (" True ", True),
            ("1", True),
            (" 1", True),
            ("false", False),
            ("FALSE", False),
            (" False ", False),
            ("0", False),
            ("yes", None),
            ("no", None),
            ("2", None),
            ("banana", None),
            ("", None),
        ],
    )
    def test_fixed_grammar_tokens(self, token: str, expected: bool | None) -> None:
        assert _map_flag_token(token) is expected

    def test_null_and_nan_map_to_null(self) -> None:
        assert _map_flag_token(None) is None
        assert _map_flag_token(float("nan")) is None

    def test_unsupported_tokens_never_raise(self) -> None:
        # Totality: no token, however unexpected, may raise or warn.
        for token in ("maybe", "2", "TrueFalse", "1.0", "  ", "null", "None"):
            assert _map_flag_token(token) is None

    def test_dp_read_boxing_is_row_independent_at_the_csv_seam(self, tmp_path: Path) -> None:
        """Codex P1 regression: pandas dtype inference at the CSV read must not
        let one row reinterpret another. `01` infers as int 1 -> "1" -> True
        when a column is all-numeric, but as the string "01" -> null once any
        row forces the column to strings. DP mode reads every column as raw
        text (dtype=str), so both cases box identically. This mirrors fit.py's
        DP read + _build_typed_frame; the prior test built already-string
        frames and never exercised this seam."""
        flag_schema = {"f": {"kind": "categorical", "carrier": "flag"}}
        short = tmp_path / "short.csv"
        short.write_text("f\n01\n01\n", encoding="utf-8")
        longer = tmp_path / "long.csv"
        longer.write_text("f\n01\n01\nbanana\n", encoding="utf-8")
        boxed_short = _build_typed_frame(
            pd.read_csv(short, dtype=str, keep_default_na=False), flag_schema
        )
        boxed_long = _build_typed_frame(
            pd.read_csv(longer, dtype=str, keep_default_na=False), flag_schema
        )
        # "01" is not in the true/false/1/0 grammar, so it is null in BOTH.
        assert boxed_short["f"].tolist() == [None, None]
        assert boxed_long["f"].tolist()[:2] == boxed_short["f"].tolist()

    def test_dp_number_columns_pass_through_as_raw_strings(self, tmp_path: Path) -> None:
        """Number columns reach the engine as raw string lexemes so its per-cell
        decode_number (float(cell)) canonicalizes each independently. Codex's
        counterexample: a large integer must not be reboxed when another row is
        added. pd.to_numeric would pick int64 for the all-integer column and
        float64 once a decimal row appears, changing the released f64 for the
        big value. Passing the lexeme through keeps it identical regardless of
        the column's other values."""
        number_schema = {"n": {"kind": "numeric", "carrier": "number", "bounds": [0.0, 1e19]}}
        short = tmp_path / "s.csv"
        short.write_text("n\n9223372036854775807\n", encoding="utf-8")
        longer = tmp_path / "l.csv"
        longer.write_text("n\n9223372036854775807\n1.0\n", encoding="utf-8")
        boxed_short = _build_typed_frame(
            pd.read_csv(short, dtype=str, keep_default_na=False), number_schema
        )["n"].tolist()
        boxed_long = _build_typed_frame(
            pd.read_csv(longer, dtype=str, keep_default_na=False), number_schema
        )["n"].tolist()
        assert boxed_short == ["9223372036854775807"]
        assert boxed_long[0] == "9223372036854775807"
        assert boxed_long[1] == "1.0"

    def test_dp_text_preserves_na_lexemes_at_the_csv_seam(self, tmp_path: Path) -> None:
        """D6 text contract: genuine CSV lexemes reach the engine unchanged.
        keep_default_na=False keeps NA/null/empty as literal strings rather than
        letting pandas coerce them to NaN (which decode_text rejects as non-str)."""
        text_schema = {"t": {"kind": "categorical", "carrier": "text"}}
        src = tmp_path / "t.csv"
        # A second column keeps each row populated, so the empty `t` field is a
        # genuine empty CSV field (,) rather than a blank line pandas would skip.
        src.write_text("t,x\nNA,1\nnull,2\n,3\nreal,4\n", encoding="utf-8")
        boxed = _build_typed_frame(pd.read_csv(src, dtype=str, keep_default_na=False), text_schema)[
            "t"
        ].tolist()
        assert boxed == ["NA", "null", "", "real"]

    def test_dp_read_path_boxes_row_independently_end_to_end(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Proves fit.py's ACTUAL read path (not a reconstruction) is row
        stable: capture the frame the engine receives by stubbing
        fit_dp_snapshot. The `01` flag cell is null and the large-integer
        number cell is the unchanged raw lexeme whether or not a later row is
        added. Fails if the DP read stops using dtype=str/keep_default_na=False
        or reintroduces column-wide numeric conversion."""
        captured: dict[str, Any] = {}

        def _capture(df, column_schema, **kwargs):
            # Capture the frame the engine would fit, then stop before the
            # write path (whose shape is not what this test is about).
            captured["flags"] = df["f"].tolist()
            captured["nums"] = df["n"].tolist()
            from decoy_engine.quality.dp import DpError

            raise DpError(code="capture_stop", message="captured for the test")

        monkeypatch.setattr("decoy_engine.quality.dp.fit_dp_snapshot", _capture)

        def _run(rows: str) -> dict[str, Any]:
            src = tmp_path / f"src_{len(rows)}.csv"
            src.write_text("f,n\n" + rows, encoding="utf-8")
            runner.invoke(
                app,
                [
                    "fit",
                    str(src),
                    "--epsilon",
                    "1.0",
                    "--delta",
                    "1e-6",
                    "--dp-flag",
                    "f",
                    "--dp-number",
                    "n:0:1e19",
                ],
            )
            return dict(captured)

        short = _run("01,9223372036854775807\n")
        longer = _run("01,9223372036854775807\n0,1.0\n")
        assert short["flags"] == [None]
        assert short["nums"] == ["9223372036854775807"]
        # Adding a decimal row must not rebox the large integer already seen.
        assert longer["flags"][:1] == [None]
        assert longer["nums"][0] == "9223372036854775807"

    def test_cli_run_with_garbage_tokens_never_exits_usage_from_flag_content(
        self, tmp_path: Path
    ) -> None:
        """A source CSV whose flag column is full of tokens outside the
        grammar must reach the engine call (and there hit the uncertified-
        stack refusal) rather than fail as a CLI usage/parse error -- proof
        that no per-cell content is treated as a validation failure."""
        src = tmp_path / "garbage_flags.csv"
        pd.DataFrame(
            {
                "amount": [1.0, 2.0, 3.0] * 10,
                "is_active": ["banana", "maybe", "", "TrueFalse", "2", "nope"] * 5,
            }
        ).to_csv(src, index=False)
        result = runner.invoke(
            app,
            [
                "fit",
                str(src),
                "--epsilon",
                "1.0",
                "--delta",
                "1e-6",
                "--dp-number",
                "amount:0:10",
                "--dp-flag",
                "is_active",
            ],
        )
        # Not a usage error from the flag content: the run reaches the real
        # engine call and is refused there for the (unrelated) uncertified
        # proof stack.
        assert result.exit_code == EXIT_RUNTIME
        assert "dp_stack_uncertified" in result.output


class TestFitDpOmission:
    """D3: only declared columns are released. An undeclared source column
    is a usage error by default (never a silent drop); --dp-allow-omit
    opts in, and the itemized notice is printed."""

    def test_omitted_column_exits_usage_by_default(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        out = tmp_path / "snapshot.json"
        result = runner.invoke(
            app,
            [
                "fit",
                str(src),
                "--output",
                str(out),
                "--epsilon",
                "1.0",
                "--delta",
                "1e-6",
                "--dp-number",
                "amount:0:200",
                "--dp-text",
                "state",
                "--dp-flag",
                "is_active",
                # "notes" is left undeclared.
            ],
        )
        assert result.exit_code == EXIT_USAGE
        assert "dp_columns_omitted" in result.output
        assert "notes" in result.output
        assert not out.exists()

    def test_allow_omit_proceeds_past_the_omission_check(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        out = tmp_path / "snapshot.json"
        result = runner.invoke(
            app,
            [
                "fit",
                str(src),
                "--output",
                str(out),
                "--epsilon",
                "1.0",
                "--delta",
                "1e-6",
                "--dp-number",
                "amount:0:200",
                "--dp-text",
                "state",
                "--dp-flag",
                "is_active",
                "--dp-allow-omit",
            ],
        )
        # Past the omission check, the run reaches the real engine call and
        # is refused there for the uncertified proof stack -- proof that
        # --dp-allow-omit let the fit proceed rather than usage-erroring.
        assert result.exit_code == EXIT_RUNTIME
        assert "dp_stack_uncertified" in result.output
        assert "notes" in result.output  # the itemized notice names it
        assert not out.exists()


class TestFitDpNoArtifactOnFailure:
    """No artifact is created or overwritten when a DP fit fails, at any
    validation stage."""

    def test_no_output_written_on_mode_selection_error(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        out = tmp_path / "snapshot.json"
        result = runner.invoke(app, ["fit", str(src), "--output", str(out), "--delta", "1e-6"])
        assert result.exit_code == EXIT_USAGE
        assert not out.exists()

    def test_existing_output_not_overwritten_on_engine_failure(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        out = tmp_path / "snapshot.json"
        sentinel = "not a snapshot"
        out.write_text(sentinel, encoding="utf-8")
        result = runner.invoke(
            app,
            [
                "fit",
                str(src),
                "--output",
                str(out),
                "--epsilon",
                "1.0",
                "--delta",
                "1e-6",
                "--dp-number",
                "amount:0:200",
                "--dp-text",
                "state",
                "--dp-flag",
                "is_active",
                "--dp-allow-omit",
            ],
        )
        assert result.exit_code == EXIT_RUNTIME
        assert out.read_text(encoding="utf-8") == sentinel


class TestFitDpErrorFamilies:
    """D5: all four engine exception families are surfaced with `code` and
    `message` as separate JSON fields, mapped to the documented exit code."""

    def _dp_args(self, src: Path, **overrides: str) -> list[str]:
        args = [
            "fit",
            str(src),
            "--epsilon",
            overrides.pop("epsilon", "1.0"),
            "--delta",
            overrides.pop("delta", "1e-6"),
            "--dp-number",
            "amount:0:200",
            "--dp-text",
            "state",
            "--dp-flag",
            "is_active",
            "--dp-allow-omit",
        ]
        assert not overrides
        return args

    def test_dp_error_bad_epsilon_exits_usage(self, tmp_path: Path) -> None:
        # epsilon=0 clears mode selection (it is not None) but is invalid at
        # the engine's own parameter check, which runs BEFORE the proof-stack
        # gate -- reachable on this uncertified host, unlike the other three
        # families (see the module docstring).
        src = _dp_source_csv(tmp_path)
        result = runner.invoke(app, self._dp_args(src, epsilon="0"), catch_exceptions=False)
        assert result.exit_code == EXIT_USAGE
        assert "dp_epsilon_invalid" in result.output

    def test_dp_error_bad_epsilon_json_has_separate_code_and_message(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        result = runner.invoke(
            app, [*self._dp_args(src, epsilon="0"), "--json"], catch_exceptions=False
        )
        assert result.exit_code == EXIT_USAGE
        payload = json.loads(result.stdout)
        assert payload["code"] == "dp_epsilon_invalid"
        assert isinstance(payload["message"], str) and payload["message"]
        assert payload["code"] != payload["message"]

    def test_dp_error_bad_delta_exits_usage(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        result = runner.invoke(app, self._dp_args(src, delta="1.5"))
        assert result.exit_code == EXIT_USAGE
        assert "dp_delta_invalid" in result.output

    def test_provenance_error_exits_runtime_with_dedicated_hint(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        result = runner.invoke(app, self._dp_args(src))
        assert result.exit_code == EXIT_RUNTIME
        assert "dp_stack_uncertified" in result.output
        assert "not a certified DP platform/stack" in result.output

    def test_provenance_error_json_has_code_message_and_hint(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        result = runner.invoke(app, [*self._dp_args(src), "--json"])
        assert result.exit_code == EXIT_RUNTIME
        payload = json.loads(result.stdout)
        assert payload["code"] == "dp_stack_uncertified"
        assert payload["message"]
        assert "not a certified DP platform/stack" in payload["hint"]

    def test_carrier_error_surfaces_code_and_message(self, tmp_path: Path, monkeypatch) -> None:
        def _raise(*args, **kwargs):
            from decoy_engine.quality.carriers import CarrierError

            raise CarrierError(code="dp_carrier_bounds_order", message="synthetic carrier failure")

        monkeypatch.setattr("decoy_engine.quality.dp.fit_dp_snapshot", _raise)
        src = _dp_source_csv(tmp_path)
        result = runner.invoke(app, [*self._dp_args(src), "--json"])
        assert result.exit_code == EXIT_USAGE
        payload = json.loads(result.stdout)
        assert payload["code"] == "dp_carrier_bounds_order"
        assert payload["message"] == "synthetic carrier failure"

    def test_budget_error_infeasible_exits_usage(self, tmp_path: Path, monkeypatch) -> None:
        def _raise(*args, **kwargs):
            from decoy_engine.quality.dp_budget import DpBudgetError

            raise DpBudgetError(code="dp_budget_infeasible", message="synthetic budget failure")

        monkeypatch.setattr("decoy_engine.quality.dp.fit_dp_snapshot", _raise)
        src = _dp_source_csv(tmp_path)
        result = runner.invoke(app, [*self._dp_args(src), "--json"])
        assert result.exit_code == EXIT_USAGE
        payload = json.loads(result.stdout)
        assert payload["code"] == "dp_budget_infeasible"

    def test_budget_error_schedule_mismatch_exits_runtime(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        def _raise(*args, **kwargs):
            from decoy_engine.quality.dp_budget import DpBudgetError

            raise DpBudgetError(code="dp_schedule_mismatch", message="synthetic invariant failure")

        monkeypatch.setattr("decoy_engine.quality.dp.fit_dp_snapshot", _raise)
        src = _dp_source_csv(tmp_path)
        result = runner.invoke(app, [*self._dp_args(src), "--json"])
        assert result.exit_code == EXIT_RUNTIME
        payload = json.loads(result.stdout)
        assert payload["code"] == "dp_schedule_mismatch"

    def test_dp_error_from_engine_exits_usage(self, tmp_path: Path, monkeypatch) -> None:
        def _raise(*args, **kwargs):
            from decoy_engine.quality.dp import DpError

            raise DpError(code="dp_numeric_domain_invalid", message="synthetic domain failure")

        monkeypatch.setattr("decoy_engine.quality.dp.fit_dp_snapshot", _raise)
        src = _dp_source_csv(tmp_path)
        result = runner.invoke(app, [*self._dp_args(src), "--json"])
        assert result.exit_code == EXIT_USAGE
        payload = json.loads(result.stdout)
        assert payload["code"] == "dp_numeric_domain_invalid"


class TestFitGenerateLoop:
    def test_fit_then_generate(self, tmp_path: Path) -> None:
        src = _source_csv(tmp_path)
        snap_path = tmp_path / "snapshot.json"
        assert runner.invoke(app, ["fit", str(src), "--output", str(snap_path)]).exit_code == 0

        cfg = {
            "version": 1,
            "global_settings": {"seed": 42},
            "tables": [
                {
                    "name": "synthetic",
                    "row_count": 50,
                    "generate_columns": [
                        {
                            "name": "amount",
                            "type": "statistical",
                            "snapshot_file": str(snap_path),
                        },
                        {
                            "name": "state",
                            "type": "statistical",
                            "snapshot_file": str(snap_path),
                            "allow_real_categories": True,
                        },
                    ],
                }
            ],
            "targets": {
                "synthetic": {
                    "type": "file",
                    "format": "csv",
                    "path": str(tmp_path / "synthetic.csv"),
                }
            },
        }
        cfg_path = tmp_path / "gen.yaml"
        cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

        assert runner.invoke(app, ["validate", "config", str(cfg_path)]).exit_code == 0
        result = runner.invoke(app, ["run", str(cfg_path)])
        assert result.exit_code == 0, result.output
        out = pd.read_csv(tmp_path / "synthetic.csv")
        assert len(out) == 50
        assert set(out["state"].unique()) <= {"CA", "NY", "TX"}
        assert out["amount"].between(9.9, 100.0).all()

    def test_validate_rejects_missing_snapshot(self, tmp_path: Path) -> None:
        cfg = {
            "version": 1,
            "global_settings": {"seed": 42},
            "tables": [
                {
                    "name": "synthetic",
                    "row_count": 5,
                    "generate_columns": [
                        {
                            "name": "amount",
                            "type": "statistical",
                            "snapshot_file": str(tmp_path / "missing.json"),
                        }
                    ],
                }
            ],
            "targets": {
                "synthetic": {
                    "type": "file",
                    "format": "csv",
                    "path": str(tmp_path / "out.csv"),
                }
            },
        }
        cfg_path = tmp_path / "gen.yaml"
        cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
        result = runner.invoke(app, ["validate", "config", str(cfg_path)])
        assert result.exit_code == EXIT_USAGE
        assert "statistical_snapshot_unreadable" in result.output


class TestFitDpArtifactShape:
    """The DP artifact is a `dps-marginal/v3` release, written only on
    success. A real fit can't complete on this uncertified host (see the
    module docstring), so the write path is proven against a monkeypatched
    `fit_dp_snapshot` returning a shape matching the real one."""

    def _fake_dp_artifact(self) -> dict:
        return {
            "schema_version": "distribution-snapshot/v1",
            "row_count": 40,
            "columns": {
                "amount": {"kind": "numeric", "carrier": "number"},
                "state": {"kind": "categorical", "carrier": "text"},
                "is_active": {"kind": "categorical", "carrier": "flag"},
            },
            "joints": [],
            "dp": {"schema": "dps-marginal/v3", "epsilon_total": 1.0, "delta_total": 1e-6},
        }

    def test_dp_artifact_is_written_only_on_success_with_v3_schema(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        fake = self._fake_dp_artifact()
        monkeypatch.setattr("decoy_engine.quality.dp.fit_dp_snapshot", lambda *a, **k: fake)
        src = _dp_source_csv(tmp_path)
        out = tmp_path / "snapshot.json"
        result = runner.invoke(
            app,
            [
                "fit",
                str(src),
                "--output",
                str(out),
                "--epsilon",
                "1.0",
                "--delta",
                "1e-6",
                "--dp-number",
                "amount:0:200",
                "--dp-text",
                "state",
                "--dp-flag",
                "is_active",
                "--dp-allow-omit",
            ],
        )
        assert result.exit_code == 0, result.output
        written = json.loads(out.read_text(encoding="utf-8"))
        assert written["dp"]["schema"] == "dps-marginal/v3"
        assert written == fake

    def test_non_dp_artifact_is_distribution_snapshot_v1(self, tmp_path: Path) -> None:
        src = _source_csv(tmp_path)
        out = tmp_path / "snapshot.json"
        result = runner.invoke(app, ["fit", str(src), "--output", str(out)])
        assert result.exit_code == 0, result.output
        written = json.loads(out.read_text(encoding="utf-8"))
        assert written["schema_version"] == "distribution-snapshot/v1"
        assert "dp" not in written


class TestFitDpDeclaredColumnMissing:
    """A declared carrier column absent from the CSV is a coded usage error,
    surfaced by name before the flag-grammar and proof-stack steps. Regression
    for the phantom-column defect: a phantom --dp-flag crashed the flag grammar
    with a raw KeyError (breaking the --json contract), and a phantom
    --dp-number/text was misattributed to an uncertified host."""

    def test_phantom_flag_column_is_coded_json_error_not_traceback(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        out = tmp_path / "snapshot.json"
        # catch_exceptions=False fails the test if a KeyError escapes.
        result = runner.invoke(
            app,
            [
                "fit",
                str(src),
                "--output",
                str(out),
                "--epsilon",
                "1.0",
                "--delta",
                "1e-6",
                "--dp-number",
                "amount:0:200",
                "--dp-text",
                "state",
                "--dp-flag",
                "active",  # phantom: the real column is "is_active"
                "--dp-allow-omit",
                "--json",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == EXIT_USAGE
        payload = json.loads(result.stdout)
        assert payload["code"] == "dp_schema_column_missing"
        assert "active" in payload["message"]
        assert not out.exists()

    def test_phantom_number_column_reports_missing_before_proof_gate(self, tmp_path: Path) -> None:
        src = _dp_source_csv(tmp_path)
        # On this uncertified host the proof-stack gate would raise
        # dp_stack_uncertified (EXIT_RUNTIME); the name check must fire first.
        result = runner.invoke(
            app,
            [
                "fit",
                str(src),
                "--epsilon",
                "1.0",
                "--delta",
                "1e-6",
                "--dp-number",
                "amt:0:200",  # phantom: the real column is "amount"
                "--dp-text",
                "state",
                "--dp-flag",
                "is_active",
                "--dp-allow-omit",
            ],
        )
        assert result.exit_code == EXIT_USAGE
        assert "dp_schema_column_missing" in result.output
        assert "amt" in result.output
        assert "dp_stack_uncertified" not in result.output
