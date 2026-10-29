"""First-install critical section for ``install.sh`` (run via the bundled interpreter).

The shell has no portable ``flock``, and the lock must be the SAME one ``decoy upgrade``
takes (`decoy.distribution.lock`) so a bootstrap and an upgrade cannot interleave. So the
shell does download + verification, then hands the mutation here: under the lock it
re-checks that no runtime exists (the shell's early guard is only a fast refusal), renames
the verified bundle into ``versions/<version>``, flips ``current`` atomically, and writes
the PATH launcher.

The bundle being moved holds the running interpreter; everything used after the rename is
imported up front, so nothing is lazily resolved from the moved tree.

Exit codes: 0 installed; 3 an existing runtime or concurrent install (nothing touched);
4 could not place/activate (nothing installed).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from decoy.distribution import installer, layout, lock

EXIT_REFUSED = 3
EXIT_FAILED = 4


def _existing_runtime(home: Path) -> bool:
    versions = layout.versions_dir(home)
    if layout.current_link(home).is_symlink() or layout.current_link(home).exists():
        return True
    return versions.is_dir() and any(
        d.is_dir() and not d.name.startswith(".") for d in versions.iterdir()
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print("usage: python -m decoy.distribution.first_install <bundle_root> <version>", file=sys.stderr)
        return 2
    bundle_root, version = Path(argv[0]), argv[1]
    home = layout.decoy_home()
    try:
        with lock.exclusive(home):
            if _existing_runtime(home):
                print("an existing Decoy runtime is installed; refusing to overwrite it", file=sys.stderr)
                return EXIT_REFUSED
            dest = layout.version_dir(version, home)
            try:
                os.replace(bundle_root, dest)
                layout.atomic_point_current_at(version, home)
            except OSError as exc:
                shutil.rmtree(dest, ignore_errors=True)
                print(f"could not place or activate {version}: {exc} -- nothing installed", file=sys.stderr)
                return EXIT_FAILED
            installer._write_launcher_shim(home)
    except lock.InstallBusyError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_REFUSED
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
