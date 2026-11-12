"""The CLI's version literal.

The package root re-exports it as ``decoy.__version__``. Modules inside the package import it
from here, so none of them reaches up into the root facade (``.importlinter``). A release bumps
it with ``[project].version``; ``packaging_tools/smoke_install.py`` rewrites it the same way.
"""

__version__ = "0.1.0"
