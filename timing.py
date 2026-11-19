"""Pauseable Tk scheduler using simulation time (not wall-clock timers).

The GUI stays responsive while paused, but scheduled game steps and animations
retain their remaining delay until the player finishes speaking.
"""
import heapq
import itertools
import time


class PauseableClock:
    def __init__(self, root, tick_ms=25, clock=None):
        self.root = root
        self.tick_ms = tick_ms
        self.clock = clock or time.monotonic
        self.now = 0.0
        self.last = self.clock()
        self.paused = False
        self.jobs = []
        self.sequence = itertools.count()
        self.timer_id = self.root.after(self.tick_ms, self._tick)

    def _advance(self):
        current = self.clock()
        if not self.paused:
            self.now += max(0.0, current - self.last)
        self.last = current

    def schedule(self, delay, callback):
        self._advance()
        heapq.heappush(self.jobs, (self.now + max(0.0, float(delay)),
                                   next(self.sequence), callback))

    def pause(self):
        self._advance()
        self.paused = True

    def resume(self):
        self.last = self.clock()
        self.paused = False

    def clear(self):
        self.jobs.clear()

    def close(self):
        if self.timer_id is not None:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None
        self.jobs.clear()

    def _tick(self):
        self._advance()
        count = 0
        # Stop dispatch immediately if a callback requests a pause.
        while not self.paused and self.jobs and self.jobs[0][0] <= self.now and count < 100:
            _, _, callback = heapq.heappop(self.jobs)
            callback()
            count += 1
        self.timer_id = self.root.after(self.tick_ms, self._tick)