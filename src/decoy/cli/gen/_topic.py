"""The text of `decoy explain generation` and the generate section of `validate compile --explain`.

The type and option list is read from the engine's `generate_option_catalog()` each time the
topic renders, so a type the engine adds shows up with no edit here. The rest is prose about how
the CLI treats a generate pipeline.
"""

from __future__ import annotations

from typing import Any

from decoy.cli.gen._preview import declared_rows

_HEAD = """\
A generate table builds rows from column types, with no source rows in the output.

Workflow:

  decoy init source.csv --preset generate -o pipeline.yaml
                    Fit the CSV and write a config plus its snapshot file. Or run
                    `decoy fit source.csv` and write the config by hand.
  decoy run pipeline.yaml --rows 5
                    Preview a few rows of every table. Nothing is written.
  decoy run pipeline.yaml
                    Generate the tables and write the targets.
  decoy report fidelity source.csv synthetic.csv --generate
                    Score the generated file against the source.

Paths:

  A relative path in the YAML (sources, targets, snapshot_file, column_names_file,
  quarantine output_path) is read from the folder that holds the YAML file, whatever the
  working directory. A relative path on the command line is relative to the working directory.
  An absolute path is used as given.

Seed and key:

  global_settings.seed fixes a plain run: the same config and seed give the same rows. With
  --master-key (and --key-label) the key drives generation instead, and the seed is not used
  for generated tables; `decoy run` warns when both are set. Use a key when the output must
  match across machines. See `decoy explain keys`.

Warnings:

  A `statistical` column is scored against its snapshot after the build. When the overall score,
  or any one column's score, falls below global_settings.fidelity_warn_threshold, `decoy run`
  prints a warning and `--json` lists it under `warnings`. The rows are not changed.
  Repeated values and `unique` columns: `decoy explain unique`.

Column types (from the engine's registry). Options go on the column beside `name` and `type`:
"""


def _names(keys: tuple[str, ...]) -> str:
    return ", ".join(keys) if keys else "none"


def type_lines() -> list[str]:
    """One block per generate type: a line with the name, then its option lines."""
    from decoy_engine.config import generate_option_catalog

    lines: list[str] = []
    for type_, spec in generate_option_catalog().items():
        lines += [f"  {type_}", f"      required: {_names(spec.required)}"]
        lines.append(f"      optional: {_names(spec.optional)}")
        for selector, by_value in spec.required_when.items():
            for value, keys in by_value.items():
                lines.append(f"      when {selector} = {value}: requires {_names(keys)}")
    return lines


def common_options() -> tuple[str, ...]:
    from decoy_engine.config import generate_option_catalog

    catalog = generate_option_catalog()
    return next(iter(catalog.values())).common if catalog else ()


def generation_body() -> str:
    """The whole topic: prose, the catalog blocks, then the options every type accepts."""
    tail = f"\nEvery type also accepts: {_names(common_options())}."
    return _HEAD + "\n".join(type_lines()) + "\n" + tail


def generation_info(raw: dict[str, Any]) -> dict[str, Any] | None:
    """The generate tables of a config: columns, references and the build order, or `None`.

    Names, types and counts only. The order is the engine's `generation_order`, the function every
    generation route builds tables with, so the explain view cannot disagree with a run.
    """
    from decoy_engine.generation import generation_order

    tables = [
        t for t in raw.get("tables") or [] if isinstance(t, dict) and t.get("generate_columns")
    ]
    if not tables:
        return None
    references: list[dict[str, str]] = []
    out_tables: list[dict[str, Any]] = []
    for table in tables:
        columns = []
        for col in table["generate_columns"]:
            columns.append({"name": col.get("name", "?"), "type": col.get("type", "?")})
            if col.get("type") == "reference":
                references.append(
                    {
                        "table": table.get("name", "?"),
                        "column": col.get("name", "?"),
                        "reference_table": col.get("reference_table", "?"),
                        "reference_column": col.get("reference_column", "?"),
                    }
                )
        out_tables.append(
            {
                "name": table.get("name", "?"),
                "rows": declared_rows(table),
                "columns": columns,
            }
        )
    order = [{"table": name, "parents": list(parents)} for name, parents in generation_order(raw)]
    return {"tables": out_tables, "references": references, "order": order}
