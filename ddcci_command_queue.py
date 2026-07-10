from collections import OrderedDict
import threading
import time

from ddcci_screen_tuning import config


def ddcci_command_delay():
    try:
        return max(0.0, float(getattr(config, "DDCCI_COMMAND_DELAY", 0.15)))
    except (TypeError, ValueError):
        return 0.15


class DDCCommandQueue:
    def __init__(self):
        self._condition = threading.Condition()
        self._pending = OrderedDict()
        self._last_warning_at = {}
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, key, label, callback):
        with self._condition:
            self._pending[key] = (label, callback)
            self._condition.notify()

    def clear_pending(self):
        with self._condition:
            self._pending.clear()

    def _block_after_failure(self, key, label, error):
        now = time.monotonic()
        warning_interval = 2.0
        if now - self._last_warning_at.get(key, 0.0) >= warning_interval:
            self._last_warning_at[key] = now
            print(f"[WARN] {label} failed:", error)

    def _run(self):
        while True:
            with self._condition:
                while not self._pending:
                    self._condition.wait()
                key, (label, callback) = self._pending.popitem(last=False)

            try:
                callback()
            except Exception as e:
                self._block_after_failure(key, label, e)

            delay = ddcci_command_delay()
            if delay > 0:
                time.sleep(delay)


ddc_command_queue = DDCCommandQueue()


def submit_ddcci_command(key, label, callback):
    ddc_command_queue.submit(key, label, callback)


def clear_pending_ddcci_commands():
    ddc_command_queue.clear_pending()


def submit_light_values(monitor, brightness, contrast, label="Auto curve"):
    brightness = max(0, min(100, round(brightness)))
    contrast = max(0, min(100, round(contrast)))

    def apply_values():
        monitor.set_light_values(brightness, contrast)

    submit_ddcci_command("light", label, apply_values)
