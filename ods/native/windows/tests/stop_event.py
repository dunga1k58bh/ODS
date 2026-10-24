"""Exercise controller stop requests in isolated Windows consoles."""

import ctypes
from ctypes import wintypes
import importlib.util
import pathlib
import signal
import subprocess
import sys
import tempfile
import time
import uuid


kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
kernel.CreateEventW.restype = wintypes.HANDLE
kernel.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
kernel.OpenEventW.restype = wintypes.HANDLE
for name in ("SetEvent", "CloseHandle"):
    getattr(kernel, name).argtypes = [wintypes.HANDLE]
    getattr(kernel, name).restype = wintypes.BOOL
kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel.WaitForSingleObject.restype = wintypes.DWORD


def child(mode, ready_name, marker):
    stopped = False

    def interrupt(*_):
        nonlocal stopped
        if mode == "cooperate":
            stopped = True

    signal.signal(signal.SIGINT, interrupt)
    ready = kernel.OpenEventW(2, False, ready_name)
    assert ready and kernel.SetEvent(ready)
    kernel.CloseHandle(ready)
    while not stopped:
        time.sleep(0.02)
    pathlib.Path(marker).write_text("clean shutdown", encoding="utf-8")


def exercise(executable):
    handles = []
    processes = []
    with tempfile.TemporaryDirectory() as directory:
        def launch(mode, index):
            names = ["Local\\ODS-test-" + uuid.uuid4().hex for _ in range(2)]
            events = [kernel.CreateEventW(None, True, False, name) for name in names]
            assert all(events), ctypes.get_last_error()
            handles.extend(events)
            marker = pathlib.Path(directory) / str(index)
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            process = subprocess.Popen(
                [executable, "--stop-event=" + names[0], "run", sys.executable,
                 "-B", __file__, "--child", mode, names[1], str(marker)],
                creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            processes.append(process)
            assert kernel.WaitForSingleObject(events[1], 5000) == 0, "Child never became ready"
            return process, events[0], marker

        try:
            first, stop_first, first_marker = launch("cooperate", 1)
            second, stop_second, second_marker = launch("cooperate", 2)
            assert kernel.SetEvent(stop_first)
            assert first.wait(timeout=8) == 130
            assert first_marker.exists(), "Graceful cleanup did not run"
            assert second.poll() is None, "Stop escaped into another console"
            assert kernel.SetEvent(stop_second)
            assert second.wait(timeout=8) == 130 and second_marker.exists()
            ignoring, stop_ignoring, marker = launch("ignore", 3)
            start = time.monotonic()
            assert kernel.SetEvent(stop_ignoring)
            assert ignoring.wait(timeout=9) == 130
            assert time.monotonic() - start >= 4.5, "Grace period was skipped"
            assert not marker.exists()

            # Invoke the real host-agent entry point, not a copy of its launcher.
            source = pathlib.Path(__file__).resolve().parents[3] / "bin"
            sys.path.insert(0, str(source))
            spec = importlib.util.spec_from_file_location("native_test_agent", source / "ods-host-agent.py")
            agent = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = agent
            spec.loader.exec_module(agent)
            ready_name = "Local\\ODS-test-" + uuid.uuid4().hex
            ready = kernel.CreateEventW(None, True, False, ready_name)
            assert ready
            handles.append(ready)
            marker = pathlib.Path(directory) / "agent-cleanup"
            runtime = agent._start_windows_native_runtime(
                pathlib.Path(executable), pathlib.Path(sys.executable),
                ["-B", __file__, "--child", "cooperate", ready_name, str(marker)],
                pathlib.Path(directory) / "agent.log",
            )
            try:
                assert kernel.WaitForSingleObject(ready, 5000) == 0
            finally:
                runtime.stop()
            assert runtime.poll() == 130 and marker.exists()
            runtime.stop()  # Repeated stop/atexit must be harmless.
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
            for handle in handles:
                kernel.CloseHandle(handle)


if __name__ == "__main__":
    if sys.argv[1] == "--child":
        child(*sys.argv[2:])
    else:
        exercise(sys.argv[1])
