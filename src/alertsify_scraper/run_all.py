from __future__ import annotations

import logging
import signal
import subprocess
import sys

from alertsify_scraper.dashboard.app import main as dashboard_main
from alertsify_scraper.log_config import configure_logging

logger = logging.getLogger(__name__)

_SCRAPER_SHUTDOWN_TIMEOUT_S = 30.0


def _stop_scraper(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=_SCRAPER_SHUTDOWN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def main() -> None:
    configure_logging()
    logger.info(
        "Starting alertsify-run-all: scraper subprocess + dashboard on one host"
    )
    proc = subprocess.Popen([sys.executable, "-m", "alertsify_scraper"])
    try:
        dashboard_main()
    finally:
        _stop_scraper(proc)


if __name__ == "__main__":
    main()
