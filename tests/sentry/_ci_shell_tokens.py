"""Shell-command parsing for CI sentries: split step text into commands, normalise the tokens,
and read pip and uv install arguments. Repository-neutral: no policy, no file names, no engine.

The engine repository adopts this same byte-identical file after CI-E1 merges (CI-X follow-up);
ci/vendored.toml holds its sha256, so a one-sided edit fails the vendor test in either repo.
Every scanner built on it gets the same spellings for free: `/usr/bin/pip`, `pip3.11`,
`--opt=value`, glued short values (`-rfile`, `-e.`, `-ihttps://x`), and the body of
`bash -c "..."`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SEPARATORS = {"&&", "||", ";", "|"}
INDEX_OPTIONS = {"--index-url", "--extra-index-url", "-i", "--index", "--default-index"}
# Options that consume the next token and carry no package.
VALUE_OPTIONS = {
    "--python",
    "--build-constraint",
    "-f",
    "--find-links",
    "-t",
    "--target",
    "--prefix",
    "--no-binary",
    "--only-binary",
}
EXACT_PIN = re.compile(r"^[A-Za-z0-9_.\-]+(\[[A-Za-z0-9_,.\-]+\])?==[^<>=!~\s]+$")
_TOKEN = re.compile(r"\"[^\"]*\"|'[^']*'|\S+")
_TOOLS = {"uv", "uvx", "pipx", "python", "python3", "bash", "sh"}
_SHELLS = {"bash", "sh", "zsh", "dash"}
_SHORT_VALUE = re.compile(r"^-[erific].+$")
_SHELL_C = re.compile(r"^-[A-Za-z]*c$")


def is_pip(token: str) -> bool:
    return re.fullmatch(r"pip[0-9.]*", token) is not None


def base(token: str) -> str:
    return token.rsplit("/", 1)[-1]


def code_lines(text: str) -> list[str]:
    """Shell lines with continuations joined and comment-only or blank lines dropped."""
    text = re.sub(r"\\\n\s*", " ", text)
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def normalise(cmd: list[str]) -> list[str]:
    """Give `/usr/local/bin/uv` and `pip3.11` their plain names; split `--opt=value`, `-e.`, `-rX`.

    Option splitting runs only for commands that name pip, uv, uvx or pipx, so `sed -i.bak` and
    `docker run -it` keep their shape."""
    named = [
        base(t)
        if "/" in t and not t.startswith("-") and (base(t) in _TOOLS or is_pip(base(t)))
        else t
        for t in cmd
    ]
    if not any(t in {"uv", "uvx", "pipx"} or is_pip(t) for t in named):
        return named
    out: list[str] = []
    for tok in named:
        if tok.startswith("--") and "=" in tok:
            key, _, value = tok.partition("=")
            out += [key, *([value] if value else [])]
        elif _SHORT_VALUE.match(tok):
            out += [tok[:2], tok[2:]]
        else:
            out.append(tok)
    return out


def _shell_body(cmd: list[str]) -> str | None:
    """The quoted script of `bash -c "..."`, or None when the command is not that."""
    if not cmd or base(cmd[0]) not in _SHELLS:
        return None
    for i, tok in enumerate(cmd[1:-1], start=1):
        if _SHELL_C.match(tok):
            return cmd[i + 1]
    return None


def commands(text: str) -> list[list[str]]:
    """Split step text into commands of normalised tokens: comments dropped, continuations joined,
    and the body of `bash -c "..."` split into commands of its own."""
    text = text.replace('\\"', '"').replace("\\$", "$")
    split: list[list[str]] = []
    for line in code_lines(text):
        current: list[str] = []
        for raw in _TOKEN.findall(line):
            token = raw.strip("\"'") if raw[0] in "\"'" else raw
            if token.endswith(";") and len(token) > 1:
                current.append(token[:-1])
                split.append(current)
                current = []
            elif token in SEPARATORS:
                split.append(current)
                current = []
            else:
                current.append(token)
        split.append(current)
    out: list[list[str]] = []
    for cmd in (normalise(c) for c in split if c):
        out.append(cmd)
        if (body := _shell_body(cmd)) is not None:
            out += commands(body)
    return out


def pip_install_args(cmd: list[str]) -> list[str] | None:
    """Arguments after `pip install` (pip, python -m pip, uv pip), or None if not one."""
    for i, tok in enumerate(cmd):
        if not is_pip(tok):
            continue
        rest = cmd[i + 1 :]
        j = 0
        while j < len(rest) and rest[j].startswith("-"):
            j += 1
        if j < len(rest) and rest[j] == "install":
            return rest[j + 1 :]
    return None


@dataclass
class InstallArgs:
    """What one `pip install` names, sorted by role. Policy decides which of it is allowed."""

    constraints: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    index_overrides: list[str] = field(default_factory=list)
    editables: list[str] = field(default_factory=list)
    positionals: list[str] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)


def parse_install_args(args: list[str]) -> InstallArgs:
    """Sort install arguments: option values are consumed by their option, never read as packages."""
    parsed = InstallArgs()
    it = iter(args)
    for arg in it:
        if arg in {"-c", "--constraint"}:
            parsed.constraints.append(next(it, ""))
        elif arg in {"-r", "--requirement"}:
            parsed.requirements.append(next(it, ""))
        elif arg in INDEX_OPTIONS:
            parsed.index_overrides.append(arg)
            next(it, None)
        elif arg in VALUE_OPTIONS:
            next(it, None)
        elif arg in {"-e", "--editable"}:
            parsed.editables.append(next(it, ""))
        elif arg.startswith("-"):
            parsed.flags.add(arg)
        else:
            parsed.positionals.append(arg)
    return parsed


def uv_run_findings(cmd: list[str], *, frozen_env: bool = False) -> list[str]:
    """`uv run` resolves and installs on its own: `--with*` adds packages, and without `--frozen`
    (or UV_FROZEN=1 in the environment) it may re-lock."""
    after = cmd[cmd.index("uv") + 1 :] if "uv" in cmd else []
    if "run" not in after:
        return []
    found = []
    if any(t.startswith("--with") for t in after):
        found.append("uv run --with installs outside the lock")
    if "--frozen" not in after and not frozen_env:
        found.append("uv run without --frozen and no UV_FROZEN env")
    return found
