import threading
import unittest
from unittest.mock import patch

from ddcci_command_queue import DDCCommandQueue, submit_brightness
from midi_qt_signals import bus


class DDCCommandQueueTests(unittest.TestCase):
    def test_only_latest_request_for_resource_is_verified(self):
        queue = DDCCommandQueue()
        first_started = threading.Event()
        release_first = threading.Event()
        final_verified = threading.Event()
        verified = []

        def apply_first():
            first_started.set()
            release_first.wait(1.0)

        with patch("ddcci_command_queue.ddcci_command_delay", return_value=0):
            queue.submit(
                "light",
                "first",
                apply_first,
                verify=lambda resources: verified.append(("first", resources)),
                resources=("brightness", "contrast"),
            )
            self.assertTrue(first_started.wait(1.0))

            def verify_final(resources):
                verified.append(("final", resources))
                final_verified.set()

            queue.submit(
                "brightness",
                "final",
                lambda: None,
                verify=verify_final,
                resources=("brightness",),
            )
            release_first.set()

            self.assertTrue(final_verified.wait(1.0))

        self.assertEqual(
            verified,
            [
                ("first", {"contrast"}),
                ("final", {"brightness"}),
            ],
        )

    def test_verified_value_is_the_value_read_from_monitor(self):
        class FakeMonitor:
            def __init__(self):
                self.requested = None
                self.read_without_cache = False

            def set_brightness(self, value):
                self.requested = value

            def get_brightness(self, use_cache=True):
                self.read_without_cache = not use_cache
                return 37

        monitor = FakeMonitor()
        received = []

        def receive(key, value):
            received.append((key, value))

        bus.ddcci_verified.connect(receive)
        try:
            with patch("ddcci_command_queue.ddc_command_queue.submit") as submit:
                submit_brightness(monitor, 42)
                callback = submit.call_args.args[2]
                verify = submit.call_args.kwargs["verify"]
                callback()
                verify({"brightness"})
        finally:
            bus.ddcci_verified.disconnect(receive)

        self.assertEqual(monitor.requested, 42)
        self.assertTrue(monitor.read_without_cache)
        self.assertEqual(received, [("brightness", 37)])


if __name__ == "__main__":
    unittest.main()
