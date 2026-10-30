"""Keep the engine's file logger out of `decoy ci`.

Importing `decoy_engine` builds its singleton logger, which opens the cwd-relative
`logs/decoy_engine.log`, and its advisories (capacity, reroute) name user tables. A CI check
must create no artifact the leak sentry cannot vouch for and must not append to a log that
already exists. So the import happens with the cwd pointed at a throwaway directory, then the
singleton is rebuilt with no file or console sink for the duration of the checks, and the
prior logging state is restored after.

Prior art: the stdlib logging cookbook's "NullHandler for library loggers" pattern; the engine
already honours `file: null` as an explicit opt-out (`internal/logging.py`).
"""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any


@contextmanager
def engine_logging_silenced() -> Iterator[None]:
    logger = logging.getLogger("decoy_engine")
    before = list(logger.handlers)
    saved = (logger.level, logger.propagate)
    with tempfile.TemporaryDirectory(prefix="decoy-ci-") as scratch:
        origin = os.getcwd()
        os.chdir(scratch)  # the import below may open `logs/decoy_engine.log` relative to here
        engine_log: Any = None
        try:
            try:
                import decoy_engine.internal.logging as engine_log
            except ImportError:
                pass
        finally:
            os.chdir(origin)
        created = [h for h in logger.handlers if h not in before]
        try:
            prior_instance = None
            if engine_log is not None:
                prior_instance = getattr(engine_log, "_LOGGER_INSTANCE", None)
                engine_log._LOGGER_INSTANCE = None
                quiet = engine_log.get_logger({"file": None, "console": False, "level": "critical"})
                quiet.addHandler(logging.NullHandler())
                quiet.propagate = False  # root's last-resort handler would print WARNING+
            yield
        finally:
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
            for handler in before:
                logger.addHandler(handler)
            logger.setLevel(saved[0])
            logger.propagate = saved[1]
            if engine_log is not None:
                engine_log._LOGGER_INSTANCE = prior_instance
            for handler in created:
                with suppress(Exception):
                    handler.close()
