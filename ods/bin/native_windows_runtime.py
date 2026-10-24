"""Handle-owned controller for the experimental native Windows process host."""

import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import uuid


class NativeWindowsRuntime:
    def __init__(self, host: Path, executable: Path, arguments: list[str], log: Path):
        self._process = None
        self._event = None
        self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel.CreateEventW.argtypes = [
            ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        self._kernel.CreateEventW.restype = wintypes.HANDLE
        for name in ("SetEvent", "CloseHandle"):
            function = getattr(self._kernel, name)
            function.argtypes = [wintypes.HANDLE]
            function.restype = wintypes.BOOL
        name = "Local\\ODS-native-" + uuid.uuid4().hex
        self._event = self._kernel.CreateEventW(None, True, False, name)
        if not self._event:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            # A separate console confines the host's generated Ctrl+C to its
            # own children. Keep the controller's console out of that group.
            with log.open("ab") as output:
                self._process = subprocess.Popen(
                    [str(host), "--stop-event=" + name, "--child-log=" + str(log),
                     "run", str(executable), *arguments],
                    stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                    creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup,
                )
        except BaseException:
            self._kernel.CloseHandle(self._event)
            self._event = None
            raise

    def stop(self):
        """Wait for graceful shutdown, then reap the owned host if it hangs."""
        if self._event is None:
            return
        try:
            if self._process.poll() is None:
                if not self._kernel.SetEvent(self._event):
                    raise ctypes.WinError(ctypes.get_last_error())
                try:
                    self._process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    # Closing the host also closes its kill-on-close Job Object.
                    self._process.kill()
                    self._process.wait(timeout=5)
        finally:
            if self._process.poll() is not None:
                self._kernel.CloseHandle(self._event)
                self._event = None

    def poll(self):
        return self._process.poll()
