"""Handle-owned controller for the experimental native Windows process host."""

import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import uuid


def build_llama_arguments(*, model: Path, api_key_file: Path, port: int,
                         context_length: int, gpu_layers: int, backend: str) -> list[str]:
    """Build the basic single-slot launch; never write files or start processes.

    This covers CPU/CUDA text models only. Runtime qualification, key-file
    preparation, registered profiles and additional tuning belong to callers.
    """
    if backend not in {"cpu", "cuda"}:
        raise ValueError("The basic Windows launch supports only cpu and cuda")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("port must be an integer in 1..65535")
    if type(context_length) is not int or context_length < 1:
        raise ValueError("context_length must be a positive integer")
    if type(gpu_layers) is not int or gpu_layers < 0:
        raise ValueError("gpu_layers must be a nonnegative integer")
    if not model.is_absolute() or not model.is_file() or model.suffix.lower() != ".gguf":
        raise ValueError("model must be an existing absolute GGUF path")
    if not api_key_file.is_absolute() or not api_key_file.is_file():
        raise ValueError("api_key_file must be an existing absolute path")
    if not model.name.isascii():
        raise ValueError("The Windows model alias requires an ASCII filename")
    arguments = [
        "--model", str(model), "--alias", model.name,
        "--host", "127.0.0.1", "--port", str(port),
        "--ctx-size", str(context_length), "--parallel", "1",
        "--n-gpu-layers", str(gpu_layers if backend == "cuda" else 0),
        "--metrics", "--no-webui", "--api-key-file", str(api_key_file),
    ]
    if backend == "cuda":
        # Match the existing Windows runtime: retain the planned GPU settings.
        arguments.extend(["--fit", "off"])
    return arguments


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
