"""Error log in %USERPROFILE%\\.murmur\\murmur.log.

Murmur runs under pythonw, which has no console, so without this errors vanish. The log is
small and rotates. It never holds what was dictated or which keys were pressed, only events,
timings and errors.
"""
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from .history import DIR

FILE = DIR / "murmur.log"


def setup():
    """Sends the "murmur" loggers and uncaught exceptions (any thread) to the log file."""
    DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log = logging.getLogger("murmur")
    log.addHandler(handler)
    log.setLevel(logging.INFO)

    def excepthook(kind, value, tb):
        log.critical("Uncaught exception", exc_info=(kind, value, tb))
        if sys.stderr:  # also on the console, when there is one
            sys.__excepthook__(kind, value, tb)

    def thread_excepthook(args):
        if args.exc_type is SystemExit:
            return
        name = args.thread.name if args.thread else "?"
        log.critical("Uncaught exception in thread %s", name,
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    # Qt slots report their exceptions through sys.excepthook too.
    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook
