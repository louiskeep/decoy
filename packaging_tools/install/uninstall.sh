#!/bin/sh
# Decoy CLI uninstaller (POSIX). Removes the managed runtime under ~/.decoy and the
# launcher shim on PATH. Thin wrapper over `install.sh uninstall` so the removal logic
# lives in one place. Honors DECOY_HOME / DECOY_BIN_DIR.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec sh "$here/install.sh" uninstall
