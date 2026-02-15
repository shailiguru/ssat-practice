"""Countdown timer for timed test sections."""

import threading
import time
from typing import Callable, Optional


class Timer:
    """Background countdown timer.

    Runs in a daemon thread. The main thread checks is_time_up() between
    questions. The timer does NOT interrupt input() — it signals completion
    via a threading.Event.
    """

    def __init__(
        self,
        total_seconds: int,
        on_tick: Optional[Callable[[int], None]] = None,
        on_warning: Optional[Callable[[], None]] = None,
    ):
        self.total_seconds = total_seconds
        self.remaining = total_seconds
        self.time_up = threading.Event()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._on_tick = on_tick
        self._on_warning = on_warning
        self._lock = threading.Lock()
        self._warned_5min = False
        self._warned_1min = False

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop_event.is_set() and self.remaining > 0:
            time.sleep(1)
            with self._lock:
                self.remaining -= 1
                current = self.remaining

            if self._on_tick:
                self._on_tick(current)

            # Warning at 5 minutes and 1 minute
            if self._on_warning:
                if current == 300 and not self._warned_5min:
                    self._warned_5min = True
                    self._on_warning()
                elif current == 60 and not self._warned_1min:
                    self._warned_1min = True
                    self._on_warning()

            if current <= 0:
                self.time_up.set()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def is_time_up(self) -> bool:
        return self.time_up.is_set()

    def get_remaining(self) -> int:
        with self._lock:
            return self.remaining

    def get_formatted_remaining(self) -> str:
        r = self.get_remaining()
        return f"{r // 60:02d}:{r % 60:02d}"

    def get_elapsed(self) -> int:
        with self._lock:
            return self.total_seconds - self.remaining
