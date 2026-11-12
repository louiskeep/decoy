"""Duplication and cross-cutting-concern census over a Python source tree.

Usage: census.py <repo_root> <src_subdir> <out_dir>

Passes (each writes one JSON file into out_dir):
  shape.json      functions whose normalized AST is identical across sites
  calls.json      external (stdlib / third-party) call targets by module spread
  names.json      function names defined in more than one module
  cochange.json   file pairs that change together in git history
"""
from __future__ import annotations

import ast
import collections
import hashlib
import itertools
import json
import subprocess
import sys
from pathlib import Path

MIN_SHAPE_NODES = 40  # ignore trivial bodies


def iter_sources(root: Path, sub: str):
    base = root / sub
    for p in sorted(base.rglob("*.py")):
        try:
            text = p.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (SyntaxError, UnicodeDecodeError):
            continue
        yield p.relative_to(root).as_posix(), text, tree


class _Normalize(ast.NodeTransformer):
    """Erase identifiers and literal values so only structure remains."""

    def visit_Name(self, node):
        return ast.copy_location(ast.Name(id="_", ctx=node.ctx), node)

    def visit_arg(self, node):
        node.arg = "_"
        node.annotation = None
        return node

    def visit_Attribute(self, node):
        self.generic_visit(node)
        node.attr = "_"
        return node

    def visit_Constant(self, node):
        return ast.copy_location(ast.Constant(value=type(node.value).__name__), node)

    def visit_keyword(self, node):
        self.generic_visit(node)
        node.arg = "_"
        return node

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        node.name = "_"
        node.returns = None
        node.decorator_list = []
        return node

    visit_AsyncFunctionDef = visit_FunctionDef


def _strip_docstring(body):
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
            and isinstance(body[0].value.value, str):
        return body[1:]
    return body


def shape_pass(sources):
    groups = collections.defaultdict(list)
    for path, _text, tree in sources:
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = _strip_docstring(node.body)
            if not body:
                continue
            n_nodes = sum(1 for stmt in body for _ in ast.walk(stmt))
            if n_nodes < MIN_SHAPE_NODES:
                continue
            clone = ast.Module(body=[ast.parse(ast.unparse(s)).body[0] for s in body], type_ignores=[])
            norm = _Normalize().visit(clone)
            digest = hashlib.sha1(ast.dump(norm).encode()).hexdigest()[:16]
            groups[digest].append({
                "path": path, "name": node.name, "line": node.lineno,
                "end": node.end_lineno, "nodes": n_nodes,
            })
    out = []
    for digest, sites in groups.items():
        files = {s["path"] for s in sites}
        if len(sites) < 2:
            continue
        out.append({
            "hash": digest, "sites": sites, "n_sites": len(sites), "n_files": len(files),
            "nodes": sites[0]["nodes"],
            "dup_lines": sum(s["end"] - s["line"] + 1 for s in sites[1:]),
        })
    out.sort(key=lambda g: (-g["nodes"] * (g["n_sites"] - 1)))
    return out


def _import_map(tree):
    """Local name -> dotted origin, for top-level and nested imports."""
    m = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                m[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for a in node.names:
                m[a.asname or a.name] = f"{node.module}.{a.name}"
    return m


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return list(reversed(parts))
    return None


BUILTIN_PRIMITIVES = {"open", "print", "input", "eval", "exec", "hash", "id", "compile", "__import__"}


def calls_pass(sources, own_prefixes):
    by_target = collections.defaultdict(lambda: collections.defaultdict(list))
    for path, _text, tree in sources:
        imports = _import_map(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            parts = _dotted(node.func)
            if not parts:
                continue
            head = parts[0]
            if head in imports:
                target = ".".join([imports[head], *parts[1:]])
            elif len(parts) == 1 and head in BUILTIN_PRIMITIVES:
                target = f"builtins.{head}"
            else:
                continue
            if any(target == p or target.startswith(p + ".") for p in own_prefixes):
                continue
            by_target[target][path].append(node.lineno)
    out = []
    for target, files in by_target.items():
        pkgs = {str(Path(f).parent) for f in files}
        out.append({
            "target": target, "n_files": len(files), "n_packages": len(pkgs),
            "n_calls": sum(len(v) for v in files.values()),
            "files": {f: lines for f, lines in sorted(files.items())},
        })
    out.sort(key=lambda t: (-t["n_packages"], -t["n_files"]))
    return out


def names_pass(sources):
    by_name = collections.defaultdict(list)
    for path, _text, tree in sources:
        for node in tree.body:  # module-level functions only
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("__") or node.name in {"main", "_main"}:
                    continue
                body = _strip_docstring(node.body)
                by_name[node.name].append({
                    "path": path, "line": node.lineno, "end": node.end_lineno,
                    "args": [a.arg for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs],
                    "stmts": len(body),
                })
    out = []
    for name, sites in by_name.items():
        files = {s["path"] for s in sites}
        if len(files) < 2:
            continue
        out.append({"name": name, "n_files": len(files), "sites": sites,
                    "lines": sum(s["end"] - s["line"] + 1 for s in sites)})
    out.sort(key=lambda g: (-g["n_files"], -g["lines"]))
    return out


def cochange_pass(root: Path, sub: str, max_files_per_commit=25, min_together=6):
    log = subprocess.run(
        ["git", "-C", str(root), "log", "--no-merges", "--name-only", "--pretty=format:@@%h", "--", sub],
        capture_output=True, text=True, check=True).stdout
    commits = []
    for block in log.split("@@")[1:]:
        lines = [ln for ln in block.splitlines()[1:] if ln.endswith(".py") and ln.startswith(sub)]
        if 2 <= len(lines) <= max_files_per_commit:
            commits.append(sorted(set(lines)))
    solo = collections.Counter(f for c in commits for f in c)
    pair = collections.Counter()
    for c in commits:
        for a, b in itertools.combinations(c, 2):
            pair[(a, b)] += 1
    out = []
    for (a, b), n in pair.items():
        if n < min_together:
            continue
        if not (root / a).exists() or not (root / b).exists():
            continue
        if Path(a).parent == Path(b).parent:
            continue  # same package co-change is expected
        out.append({"a": a, "b": b, "together": n, "a_total": solo[a], "b_total": solo[b],
                    "coupling": round(n / min(solo[a], solo[b]), 2)})
    out.sort(key=lambda p: (-p["coupling"], -p["together"]))
    # wide commits: one change that had to touch many packages
    wide_log = subprocess.run(
        ["git", "-C", str(root), "log", "--no-merges", "--name-only", "--pretty=format:@@%h %s", "--", sub],
        capture_output=True, text=True, check=True).stdout
    wide = []
    for block in wide_log.split("@@")[1:]:
        head, *rest = block.splitlines()
        files = [ln for ln in rest if ln.endswith(".py") and ln.startswith(sub)]
        pkgs = {str(Path(f).parent) for f in files}
        if len(pkgs) >= 6:
            wide.append({"commit": head[:120], "n_files": len(files), "n_packages": len(pkgs)})
    wide.sort(key=lambda w: -w["n_packages"])
    return {"pairs": out[:300], "wide_commits": wide[:80], "n_commits": len(commits)}


def main():
    root, sub, out_dir = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    own = sys.argv[4].split(",")
    out_dir.mkdir(parents=True, exist_ok=True)
    sources = list(iter_sources(root, sub))
    results = {
        "shape": shape_pass(sources),
        "calls": calls_pass(sources, own),
        "names": names_pass(sources),
        "cochange": cochange_pass(root, sub),
    }
    for key, val in results.items():
        (out_dir / f"{key}.json").write_text(json.dumps(val, indent=1))
    loc = sum(t.count("\n") for _p, t, _tree in sources)
    shape = results["shape"]
    print(f"{root.name}: {len(sources)} files, {loc} lines")
    print(f"  shape groups: {len(shape)}  duplicated lines: {sum(g['dup_lines'] for g in shape)}")
    print(f"  external call targets in >=5 packages: {sum(1 for t in results['calls'] if t['n_packages'] >= 5)}")
    print(f"  names in >=2 files: {len(results['names'])}  in >=4 files: {sum(1 for n in results['names'] if n['n_files'] >= 4)}")
    print(f"  cochange pairs: {len(results['cochange']['pairs'])}  wide commits: {len(results['cochange']['wide_commits'])}")


if __name__ == "__main__":
    main()
