import ctypes
import os
import threading
import time
import unittest
from types import SimpleNamespace
from app.windows import ScrollLockListener

@unittest.skipUnless(os.name == 'nt', 'Windows only')
class HotkeyTests(unittest.TestCase):
    def test_register_dispatch_and_unregister(self):
        called = threading.Event()
        service = SimpleNamespace(hotkey_ready=False, hotkey_error=None, trigger=called.set)
        listener = ScrollLockListener(service)
        listener.start()
        try:
            deadline = time.monotonic() + 2
            while not service.hotkey_ready and not service.hotkey_error and time.monotonic() < deadline:
                time.sleep(.01)
            if getattr(service, 'hotkey_error_code', None) == 5:
                self.skipTest('Windows sandbox denied global hotkey registration (error 5)')
            self.assertIsNone(service.hotkey_error)
            self.assertTrue(service.hotkey_ready)
            # Dispatch to our own message queue; no key injection or real screenshot.
            ctypes.windll.user32.PostThreadMessageW(listener.thread_id, 0x0312, 1, 0)
            self.assertTrue(called.wait(2))
        finally:
            listener.stop()
        self.assertFalse(service.hotkey_ready)
        self.assertFalse(listener.thread.is_alive())
