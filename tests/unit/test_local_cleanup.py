"""F26 Slice 5 acceptance: A21 (dry-run-first, stateless), A22 (exact execution), A23 (stable
contract). Real files in temp directories; nothing is mocked past the asserted boundary."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli import local_cleanup as lc
from decoy.cli.evidence import compute_manifest_hash, verify_manifest

runner = CliRunner()
CANARY = "CANARY_PRIVATE_NAME"


def _fp(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class Run:
    """A finished local run: an input, a pipeline, two declared outputs, a manifest."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.out = tmp / "out"
        self.out.mkdir()
        self.inp = tmp / "customers.csv"
        self.inp.write_text("id,name\n1,Ada\n")
        self.pipe = tmp / "pipeline.yaml"
        self.pipe.write_text("sources: {}\n")
        self.a = self.out / f"{CANARY}_a.csv"
        self.b = self.out / "b.csv"
        self.a.write_text("masked,a\n" * 5)
        self.b.write_text("masked,b\n" * 7)
        self.other = self.out / "unrelated.txt"
        self.other.write_text("not in the manifest")
        self.manifest = tmp / "evidence.json"
        self.write_manifest()

    def entry(self, p: Path) -> dict:
        return {
            "path": str(p),
            "fingerprint": _fp(p),
            "fingerprint_method": "full",
            "size_bytes": p.stat().st_size,
        }

    def write_manifest(self, **over):
        m = {
            "schema_version": "cli-local-1",
            "producer": "decoy-cli",
            "run_id": "r",
            "pipeline_path": str(self.pipe),
            "input_fingerprints": {"t": self.entry(self.inp)},
            "manifest_hash": "",
        }
        if "output_fingerprints" not in over:
            m["output_fingerprints"] = {"t_a": self.entry(self.a), "t_b": self.entry(self.b)}
        m.update(over)
        m["manifest_hash"] = compute_manifest_hash(m)
        self.manifest.write_text(json.dumps(m))
        return m

    def invoke(self, *args, env=None, input=None):
        return runner.invoke(
            app,
            ["local-cleanup", "--manifest", str(self.manifest), "--root", str(self.out), *args],
            env=env,
            input=input,
        )


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.delenv(lc.TOKEN_ENV, raising=False)
    monkeypatch.setattr(lc, "_is_tty", lambda: False)
    return Run(tmp_path)


def tree(p: Path):
    return sorted((str(q.relative_to(p)), q.stat().st_mtime_ns) for q in p.rglob("*"))


def report(res):
    return json.loads(res.stdout)


# ------------------------------------------------------------------------------ A21


def test_a21_dry_run_is_the_default_deletes_nothing_and_writes_nothing(run, tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path / "out")
    before = tree(tmp_path)
    res = run.invoke("--json")
    assert res.exit_code == 0, res.stdout
    assert tree(tmp_path) == before  # no hidden catalog, workspace, cache or temp file anywhere
    rep = report(res)
    assert rep["schema"] == "retention-report/v1" and rep["kind"] == "preview"
    assert (rep["counts"]["total"], rep["counts"]["eligible"]) == (2, 2)
    assert run.a.exists() and run.b.exists()


def test_a21_only_declared_outputs_are_candidates(run):
    rep = report(run.invoke("--json"))
    assert rep["counts"]["total"] == 2  # not the input, pipeline, manifest or the unrelated file
    run.invoke(
        "--execute",
        "--confirm-digest",
        rep["digest"],
        "--owner-token",
        "t",
        env={lc.TOKEN_ENV: "t"},
    )
    assert run.inp.exists() and run.pipe.exists() and run.manifest.exists() and run.other.exists()


def test_a21_output_is_value_free(run):
    res = run.invoke("--json")
    text = run.invoke()
    for blob in (res.stdout, res.stderr or "", text.stdout, text.stderr or ""):
        assert CANARY not in blob and str(run.tmp) not in blob and ".csv" not in blob
        assert "masked" not in blob and "Ada" not in blob


def test_a21_declared_inputs_pipeline_and_manifest_are_never_deleted_even_if_listed_as_outputs(run):
    run.write_manifest(
        output_fingerprints={
            "in": {**run.entry(run.inp), "path": str(run.inp)},
            "pl": {**run.entry(run.pipe), "path": str(run.pipe)},
        }
    )
    # the manifest itself can not appear (its hash covers it), but the others can be listed
    # by a hostile or buggy manifest; they are protected by inode, not by name
    rep = report(run.invoke("--json"))
    assert rep["counts"]["eligible"] == 0 and set(rep["reason_counts"]) == {"retain_unregistered"}


# ------------------------------------------------------------------------------ A22


def _digest(run):
    return report(run.invoke("--json"))["digest"]


def test_a22_execute_without_the_digest_or_with_a_wrong_one_refuses(run):
    d = _digest(run)
    for args in (
        ["--execute"],
        ["--execute", "--confirm-digest", "0" * 64],
        ["--execute", "--confirm-digest", d[:-1] + ("0" if d[-1] != "0" else "1")],
    ):
        res = run.invoke(*args, "--owner-token", "t", "--json", env={lc.TOKEN_ENV: "t"})
        assert res.exit_code == 13 and report(res)["refusal"] == "refused_digest_mismatch"
    assert run.a.exists() and run.b.exists()


def test_a22_execute_without_a_fresh_confirmation_refuses(run):
    d = _digest(run)
    res = run.invoke("--execute", "--confirm-digest", d, "--json")  # no TTY, no token
    assert res.exit_code == 13 and report(res)["refusal"] == "refused_confirmation"
    res = run.invoke(
        "--execute",
        "--confirm-digest",
        d,
        "--owner-token",
        "wrong",
        "--json",
        env={lc.TOKEN_ENV: "right"},
    )
    assert report(res)["refusal"] == "refused_confirmation"
    res = run.invoke(
        "--execute", "--confirm-digest", d, "--owner-token", "", "--json", env={lc.TOKEN_ENV: ""}
    )
    assert report(res)["refusal"] == "refused_confirmation"
    assert run.a.exists()


def test_a22_exact_eligible_outputs_are_removed_and_the_manifest_remains(run):
    d = _digest(run)
    res = run.invoke(
        "--execute",
        "--confirm-digest",
        d,
        "--owner-token",
        "tok",
        "--json",
        env={lc.TOKEN_ENV: "tok"},
    )
    assert res.exit_code == 0, res.stdout
    rep = report(res)
    assert (
        rep["kind"] == "execute" and rep["counts"]["deleted"] == 2 and rep["outcome"] == "success"
    )
    assert (
        not run.a.exists() and not run.b.exists() and run.manifest.exists() and run.other.exists()
    )
    # later verification can still report the outputs truthfully as missing
    issues = verify_manifest(json.loads(run.manifest.read_text()))
    assert any("output" in i.lower() for i in issues)
    again = run.invoke("--json")  # nothing left to do: stable no-op, not an error
    assert again.exit_code == 11 and report(again)["counts"]["eligible"] == 0


def test_a22_tty_confirmation_requires_typing_the_digest_prefix(run, monkeypatch):
    monkeypatch.setattr(lc, "_is_tty", lambda: True)
    d = _digest(run)
    res = run.invoke("--execute", "--confirm-digest", d, "--json", input="nope\n")
    assert res.exit_code == 13 and run.a.exists()
    res = run.invoke("--execute", "--confirm-digest", d, "--json", input=d[:12] + "\n")
    assert res.exit_code == 0 and not run.a.exists()


@pytest.mark.parametrize("drift", ["content", "size", "inode", "symlink", "mtime_only"])
def test_a22_any_change_since_the_preview_changes_the_digest_and_refuses(run, drift, tmp_path):
    d = _digest(run)
    if drift == "content":
        run.a.write_text("MASKED,a\n" * 5)  # same size, different bytes
    elif drift == "size":
        run.a.write_text("longer content than before, definitely\n")
    elif drift == "inode":
        data = run.a.read_bytes()
        run.a.unlink()
        run.a.write_bytes(data)
        os.utime(run.a, ns=(1_000_000_000, 1_000_000_000))
    elif drift == "symlink":
        victim = tmp_path / "victim.txt"
        victim.write_text("precious")
        run.a.unlink()
        os.symlink(victim, run.a)
    elif drift == "mtime_only":
        os.utime(run.a, ns=(2_000_000_000, 2_000_000_000))
    res = run.invoke(
        "--execute", "--confirm-digest", d, "--owner-token", "t", "--json", env={lc.TOKEN_ENV: "t"}
    )
    assert res.exit_code == 13 and report(res)["refusal"] == "refused_digest_mismatch"
    assert run.b.exists()
    if drift == "symlink":
        assert (tmp_path / "victim.txt").read_text() == "precious"


def test_a22_a_file_replaced_after_the_second_inventory_is_retained_not_deleted(
    run, monkeypatch, tmp_path
):
    d = _digest(run)
    victim = tmp_path / "victim.txt"
    victim.write_text("precious")
    real = lc.io.unlink_exact
    calls = {"n": 0}

    def swap_then_unlink(root_fd, parts, expected):
        calls["n"] += 1
        if calls["n"] == 1:  # the race window: swap the first file for a symlink just before unlink
            p = run.out / parts[-1]
            p.unlink()
            os.symlink(victim, p)
        return real(root_fd, parts, expected)

    monkeypatch.setattr(lc.io, "unlink_exact", swap_then_unlink)
    res = run.invoke(
        "--execute", "--confirm-digest", d, "--owner-token", "t", "--json", env={lc.TOKEN_ENV: "t"}
    )
    rep = report(res)
    assert res.exit_code == 12 and rep["counts"]["deleted"] == 1 and rep["counts"]["failed"] == 1
    assert victim.read_text() == "precious"


def test_a22_outside_root_hardlinked_nonregular_and_unreadable_are_retained(run, tmp_path):
    outside = tmp_path / "elsewhere" / "o.csv"
    outside.parent.mkdir()
    outside.write_text("data,out\n")
    linked = run.out / "linked.csv"
    linked.write_text("hard,link\n")
    os.link(linked, tmp_path / "alias.csv")
    sub = run.out / "dir.csv"
    sub.mkdir()
    run.write_manifest(
        output_fingerprints={
            "o": run.entry(outside),
            "h": run.entry(linked),
            "d": {"path": str(sub), "fingerprint": "sha256:" + "0" * 64, "size_bytes": 0},
            "m": {
                "path": str(run.out / "missing.csv"),
                "fingerprint": "sha256:" + "1" * 64,
                "size_bytes": 3,
            },
            "z": {"path": None, "fingerprint": None, "size_bytes": None},
        }
    )
    rep = report(run.invoke("--json"))
    assert rep["counts"]["eligible"] == 0 and rep["counts"]["total"] == 5
    assert {i["reason"] for i in rep["items"]} <= {
        "retain_unregistered",
        "retain_identity_mismatch",
        "retain_identity_unreadable",
    }
    assert outside.exists() and linked.exists() and sub.exists()


def test_a22_unreadable_file_is_retained(run):
    if os.geteuid() != 0:
        pytest.skip("drop-privilege path needs root")
    import decoy_engine.retention  # noqa: F401  (import before dropping privileges)

    for p in (run.tmp, run.tmp.parent, run.tmp.parent.parent):
        os.chmod(p, 0o755)  # traversable by the unprivileged user; only one file is not readable
    for p in (run.out, run.manifest, run.a, run.inp, run.pipe):
        os.chmod(p, 0o755 if p.is_dir() else 0o644)
    run.b.chmod(0o000)
    os.seteuid(65534)
    try:
        res = run.invoke("--json")
    finally:
        os.seteuid(0)
    rep = report(res)
    reasons = {i["reason"] for i in rep["items"]}
    assert rep["counts"]["eligible"] == 1 and "retain_identity_unreadable" in reasons
    assert run.b.exists() and run.a.exists()


@pytest.mark.parametrize(
    "breakage", ["badjson", "wrong_schema", "wrong_producer", "tampered", "not_a_dict", "missing"]
)
def test_a22_malformed_or_unverifiable_manifests_refuse(run, breakage):
    text = run.manifest.read_text()
    if breakage == "badjson":
        run.manifest.write_text("{not json")
    elif breakage == "wrong_schema":
        run.write_manifest(schema_version="cli-local-2")
    elif breakage == "wrong_producer":
        run.write_manifest(producer="somebody-else")
    elif breakage == "tampered":
        m = json.loads(text)
        m["output_fingerprints"]["t_a"]["path"] = str(run.inp)  # hash left stale
        run.manifest.write_text(json.dumps(m))
    elif breakage == "not_a_dict":
        run.manifest.write_text("[1,2,3]")
    elif breakage == "missing":
        run.manifest.unlink()
    res = run.invoke("--json")
    assert res.exit_code == 13 and report(res)["refusal"] == "refused_manifest_invalid"
    assert run.a.exists() and run.inp.exists()


def test_a22_relative_paths_resolve_against_the_manifest_directory_and_roots_must_exist(run):
    rel = os.path.relpath(run.b, run.tmp)
    run.write_manifest(output_fingerprints={"t_b": {**run.entry(run.b), "path": rel}})
    assert report(run.invoke("--json"))["counts"]["eligible"] == 1
    res = runner.invoke(
        app, ["local-cleanup", "--manifest", str(run.manifest), "--root", str(run.tmp / "nope")]
    )
    assert res.exit_code == 1  # the CLI's usage-error code


def test_a22_execution_refuses_where_safe_open_is_unavailable_but_preview_works(run, monkeypatch):
    d = _digest(run)
    monkeypatch.setattr(lc.io, "safe_open_supported", lambda: False)
    res = run.invoke(
        "--execute", "--confirm-digest", d, "--owner-token", "t", "--json", env={lc.TOKEN_ENV: "t"}
    )
    assert (
        res.exit_code == 13
        and report(res)["refusal"] == "refused_unsafe_platform"
        and run.a.exists()
    )
    assert run.invoke("--json").exit_code == 0


# ------------------------------------------------------------------------------ A23


def test_a23_json_schema_reason_codes_and_exit_codes_come_from_the_shared_engine_contract():
    from decoy_engine import retention as r

    rep_codes = set(
        re.findall(r"R\.(RETAIN_\w+|REFUSED_\w+|RESULT_\w+)", Path(lc.__file__).read_text())
    )
    known = {c.name for c in r.ReasonCode}
    assert rep_codes <= known, (
        f"local-cleanup uses codes the engine contract does not define: {rep_codes - known}"
    )
    assert {int(e) for e in r.ExitCode} == {0, 10, 11, 12, 13, 14}
    assert r.REPORT_SCHEMA == "retention-report/v1"


def test_a23_exit_codes_cover_success_noop_retained_partial_refused(run, tmp_path):
    d = _digest(run)
    assert run.invoke("--json").exit_code == 0
    assert (
        run.invoke(
            "--execute", "--confirm-digest", d, "--owner-token", "t", env={lc.TOKEN_ENV: "t"}
        ).exit_code
        == 0
    )
    assert run.invoke("--json").exit_code == 11  # declared outputs now gone: everything retained
    run.write_manifest(output_fingerprints={})
    assert run.invoke("--json").exit_code == 10  # nothing declared: no-op
    assert run.invoke("--execute", "--confirm-digest", "x", "--json").exit_code == 13


def test_a23_human_output_is_counts_and_opaque_ids_only(run):
    out = run.invoke().stdout
    body = out.split("\n", 1)[1]
    assert "retention-report/v1" in out and "digest:" in out
    assert not re.search(r"[/\\]", body) and ".csv" not in out and CANARY not in out


def test_a23_report_fields_are_allow_listed_by_the_engine_serializer(run):
    from decoy_engine.retention import ALLOWED_ITEM_KEYS, ALLOWED_REPORT_KEYS

    rep = report(run.invoke("--json"))
    assert set(rep) == ALLOWED_REPORT_KEYS and all(
        set(i) == ALLOWED_ITEM_KEYS for i in rep["items"]
    )


def test_the_command_is_registered_and_hidden_state_free():
    res = runner.invoke(app, ["local-cleanup", "--help"])
    assert res.exit_code == 0 and "--execute" in res.stdout and "--manifest" in res.stdout
    assert "--force" not in res.stdout and "--yes" not in res.stdout


def test_preview_works_without_dir_fd_support_and_still_refuses_symlinks(
    run, monkeypatch, tmp_path
):
    """Platforms without dir_fd/O_NOFOLLOW (e.g. Windows) keep a READ-ONLY preview; execution refuses."""
    monkeypatch.setattr(lc.io, "safe_open_supported", lambda: False)
    rep = report(run.invoke("--json"))
    assert rep["counts"]["eligible"] == 2
    victim = tmp_path / "victim.txt"
    victim.write_text("precious")
    run.a.unlink()
    os.symlink(victim, run.a)
    rep = report(run.invoke("--json"))
    assert rep["counts"]["eligible"] == 1 and "retain_identity_mismatch" in rep["reason_counts"]
    d = rep["digest"]
    res = run.invoke(
        "--execute", "--confirm-digest", d, "--owner-token", "t", "--json", env={lc.TOKEN_ENV: "t"}
    )
    assert res.exit_code == 13 and report(res)["refusal"] == "refused_unsafe_platform"
    assert victim.read_text() == "precious" and run.b.exists()


# ------------------------------------------------------------------------------ r2: exact handle


def _digest(run):
    return report(run.invoke("--json"))["digest"]


def test_r2_a_swap_after_verification_never_destroys_the_replacement(run, monkeypatch):
    """Deletion acts on the VERIFIED object: a file swapped in between 'verified' and 'removed' is
    restored, never deleted."""
    from decoy.cli import _local_cleanup_io as io

    digest = _digest(run)
    replacement = run.out / "replacement.csv"
    replacement.write_text("a precious DIFFERENT file")

    def swap(_fd, name):
        if name == run.a.name:  # only the first declared output is raced
            os.replace(replacement, run.a)

    monkeypatch.setattr(io, "_after_verify", swap, raising=False)
    res = run.invoke("--execute", "--confirm-digest", digest, "--owner-token", "t", "--json",
                     env={lc.TOKEN_ENV: "t"})  # fmt: skip
    assert run.a.read_text() == "a precious DIFFERENT file"  # the replacement survives, intact
    assert not run.b.exists()  # the untouched declared output was still removed
    assert report(res)["counts"]["deleted"] == 1  # exactly the unraced output


def test_r2_a_swapped_root_between_inventory_and_delete_refuses(run, monkeypatch, tmp_path):
    """The recorded ROOT device/inode is re-checked when the delete phase reopens the root."""
    from decoy.cli import _local_cleanup_io as io

    digest = _digest(run)
    real = io.open_root
    calls = {"n": 0}

    def swapping(root):
        calls["n"] += 1
        if calls["n"] == 2:  # the delete phase reopen; the inventory recompute was call 1
            moved = tmp_path / "out-moved"
            run.out.rename(moved)
            run.out.mkdir()
            for p in moved.iterdir():
                os.rename(p, run.out / p.name)  # same inodes, new root directory
        return real(root)

    monkeypatch.setattr(io, "open_root", swapping)
    res = run.invoke("--execute", "--confirm-digest", digest, "--owner-token", "t", "--json",
                     env={lc.TOKEN_ENV: "t"})  # fmt: skip
    assert run.a.exists() and run.b.exists()
    assert report(res)["counts"]["deleted"] == 0
