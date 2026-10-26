"""Point the managed-runtime ``current`` symlink at a version (installer helper).

A one-line CLI over `decoy.distribution.layout.atomic_point_current_at`, run by `install.sh`
through the bundled interpreter so the install reuses the exact atomic-swap primitive
`decoy upgrade` uses (replace a temp symlink over ``current``: a reader sees the old or
new target, never a missing link). Honors ``DECOY_HOME``.
"""

from __future__ import annotations

import sys

from decoy.distribution import layout


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: python -m decoy.distribution.layout_point <version>", file=sys.stderr)
        return 2
    layout.atomic_point_current_at(argv[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
