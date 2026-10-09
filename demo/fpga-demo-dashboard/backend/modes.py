"""ModeManager — holds the active controller and switches LIVE / DRY-RUN / REPLAY.

A single instance is created in main.py. Switching tears down the previous
controller (closing any ssh repl) and builds the new one.
"""
from __future__ import annotations

import threading

from . import config
from .controller import Controller, ReplayController
from .links import FakeKit, KitLink

VALID = ("LIVE", "DRY-RUN", "REPLAY")


class ModeManager:
    def __init__(self, initial: str = "DRY-RUN"):
        self._lock = threading.Lock()
        self._ctrl = None
        self._mode = None
        self._replay_file = config.DEFAULT_REPLAY_FILE
        self.set_mode(initial)

    def set_mode(self, mode: str, replay_file: str | None = None) -> str:
        mode = mode.upper()
        if mode not in VALID:
            raise ValueError(f"invalid mode {mode!r}; one of {VALID}")
        with self._lock:
            if self._ctrl is not None:
                try:
                    self._ctrl.close()
                except Exception:
                    pass
            if mode == "LIVE":
                self._ctrl = Controller(KitLink())
            elif mode == "DRY-RUN":
                self._ctrl = Controller(FakeKit())
            else:  # REPLAY
                rf = replay_file or self._replay_file
                self._replay_file = rf
                self._ctrl = ReplayController(config.REPLAY_DIR / rf)
            self._mode = mode
        return self._mode

    def current(self):
        with self._lock:
            return self._ctrl

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def replay_file(self) -> str:
        return self._replay_file
