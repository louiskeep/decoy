"""Keep the engine's logger quiet inside `decoy ci`.

The engine's advisories (capacity, reroute) name user tables, and a CI check must create no
artifact the leak sentry cannot vouch for. The engine opens no log file by default, so nothing
touches the working directory. Importing `decoy_engine` still builds its singleton logger, so it
is rebuilt with no file or console sink for the duration of the checks, and the prior logging
state is restored after.

Prior art: the stdlib logging cookbook's "NullHandler for library loggers" pattern; the engine
already honours `file: null` as an explicit opt-out (`internal/logging.py`).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any


@contextmanager
def engine_logging_silenced() -> Iterator[None]:
    logger = logging.getLogger("decoy_engine")
    before = list(logger.handlers)
    saved = (logger.level, logger.propagate)
    engine_log: Any = None
    try:
        import decoy_engine.internal.logging as engine_log
    except ImportError:
        pass
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
