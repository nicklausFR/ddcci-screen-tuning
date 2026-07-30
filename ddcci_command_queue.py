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
        self._resource_versions = {}
        self._last_warning_at = {}
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, key, label, callback, verify=None, resources=()):
        with self._condition:
            resource_versions = {}
            for resource in resources:
                version = self._resource_versions.get(resource, 0) + 1
                self._resource_versions[resource] = version
                resource_versions[resource] = version
            self._pending[key] = (label, callback, verify, resource_versions)
            self._condition.notify()

    def clear_pending(self):
        with self._condition:
            self._pending.clear()
            for resource in self._resource_versions:
                self._resource_versions[resource] += 1

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
                key, (label, callback, verify, resource_versions) = self._pending.popitem(last=False)

            succeeded = False
            try:
                callback()
                succeeded = True
            except Exception as e:
                self._block_after_failure(key, label, e)

            delay = ddcci_command_delay()
            if delay > 0:
                time.sleep(delay)

            if succeeded and verify is not None:
                with self._condition:
                    latest_resources = {
                        resource
                        for resource, version in resource_versions.items()
                        if self._resource_versions.get(resource) == version
                    }
                if latest_resources:
                    try:
                        verify(latest_resources)
                    except Exception as e:
                        self._block_after_failure(key, f"{label} verification", e)
                    if delay > 0:
                        time.sleep(delay)


ddc_command_queue = DDCCommandQueue()


def submit_ddcci_command(key, label, callback, verify=None, resources=()):
    ddc_command_queue.submit(
        key,
        label,
        callback,
        verify=verify,
        resources=resources,
    )


def clear_pending_ddcci_commands():
    ddc_command_queue.clear_pending()


def submit_light_values(monitor, brightness, contrast, label="Auto curve"):
    brightness = max(0, min(100, round(brightness)))
    contrast = max(0, min(100, round(contrast)))

    def apply_values():
        monitor.set_light_values(brightness, contrast)

    def verify_values(resources):
        from midi_qt_signals import bus
        if "brightness" in resources:
            actual_brightness = monitor.get_brightness(use_cache=False)
            bus.ddcci_verified.emit("brightness", actual_brightness)
        if "brightness" in resources and "contrast" in resources:
            delay = ddcci_command_delay()
            if delay > 0:
                time.sleep(delay)
        if "contrast" in resources:
            actual_contrast = monitor.get_contrast(use_cache=False)
            bus.ddcci_verified.emit("contrast", actual_contrast)

    submit_ddcci_command(
        "light",
        label,
        apply_values,
        verify=verify_values,
        resources=("brightness", "contrast"),
    )


def submit_brightness(monitor, value, label="Brightness set"):
    value = max(0, min(100, round(value)))

    def apply_value():
        monitor.set_brightness(value)

    def verify_value(_resources):
        actual = monitor.get_brightness(use_cache=False)
        from midi_qt_signals import bus
        bus.ddcci_verified.emit("brightness", actual)

    submit_ddcci_command(
        "brightness",
        label,
        apply_value,
        verify=verify_value,
        resources=("brightness",),
    )


def submit_contrast(monitor, value, label="Contrast set"):
    value = max(0, min(100, round(value)))

    def apply_value():
        monitor.set_contrast(value)

    def verify_value(_resources):
        actual = monitor.get_contrast(use_cache=False)
        from midi_qt_signals import bus
        bus.ddcci_verified.emit("contrast", actual)

    submit_ddcci_command(
        "contrast",
        label,
        apply_value,
        verify=verify_value,
        resources=("contrast",),
    )
