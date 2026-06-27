import logging
import time

logger = logging.getLogger(__name__)


class LatencyTracker:
    def __init__(self) -> None:
        self._timers: dict[str, float] = {}

    def start(self, name: str) -> None:
        self._timers[name] = time.monotonic()

    def stop(self, name: str) -> float:
        start = self._timers.pop(name, None)
        if start is None:
            return 0.0
        elapsed = time.monotonic() - start
        logger.debug("Latency [%s]: %.3f s", name, elapsed)
        return elapsed
