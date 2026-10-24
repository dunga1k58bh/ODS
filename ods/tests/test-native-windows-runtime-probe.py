"""Exercise the native bridge against the real host-agent proof implementation."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import socket
import sys
import tempfile
import time
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import Mock, patch


SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "native_probe_bridge", SOURCE / "native/windows/runtime_probe.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class NativeProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = bridge.load_host_agent()

    def invoke(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["probe", "--port", "18080", "--model", "Qwen.gguf"]), \
                patch.object(bridge.signal, "signal"), contextlib.redirect_stdout(output):
            code = bridge.main()
        return code, json.loads(output.getvalue())

    def test_reuses_identity_props_and_completion_contract(self):
        replies = {
            "/health": {"status": "ok"},
            "/v1/models": {"data": [{"id": "Qwen.gguf"}]},
            "/props": {"model_path": "/models/Qwen.gguf",
                       "default_generation_settings": {"n_ctx": 4096}},
            "/v1/chat/completions": {"model": "Qwen.gguf", "choices": [
                {"message": {"content": "READY"}}]},
        }
        visited = []

        def curl(command, **kwargs):
            url = next(arg for arg in command if arg.startswith("http://"))
            endpoint = url.removeprefix("http://127.0.0.1:18080")
            visited.append(endpoint)
            return subprocess.CompletedProcess(command, 0, json.dumps(replies[endpoint]), "")

        with patch.object(bridge, "load_host_agent", return_value=self.agent), \
                patch.object(self.agent.subprocess, "run", side_effect=curl):
            code, result = self.invoke()
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["detail"], "")
        self.assertEqual(result["proof"]["identity"], "Qwen.gguf")
        self.assertEqual(result["proof"]["contextLength"], 4096)
        self.assertEqual(visited, list(replies))

    def test_failed_proof_is_not_reported_ready(self):
        with patch.object(bridge, "load_host_agent", return_value=self.agent), \
                patch.object(self.agent, "_wait_for_model_readiness", return_value={}):
            code, result = self.invoke()
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])


class NativeAgentStartupTests(unittest.TestCase):
    def test_context_http_success_validation_and_rollback(self):
        agent = bridge.load_host_agent()
        agent.AGENT_API_KEY = "test-context-key"
        server = agent.ThreadedHTTPServer(("127.0.0.1", 0), agent.NativeWindowsAgentHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        origin = f"http://127.0.0.1:{server.server_port}/v1/native/context"

        def request(body, authenticated=True):
            headers = {"Authorization": "Bearer test-context-key"} if authenticated else {}
            req = urllib.request.Request(origin, data=json.dumps(body).encode(), headers=headers)
            try:
                response = urllib.request.urlopen(req, timeout=3)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                return response.code, json.load(response)

        try:
            with patch.object(agent, "load_env", return_value={"ODS_NATIVE_HOST_EXE": "configured"}), \
                    patch.object(agent, "_restart_experimental_windows_native") as restart:
                self.assertEqual(request({"context_length": 8192}, False)[0], 401)
                restart.assert_not_called()
                for body in ({"context_length": True}, {"context_length": 0}, {"model": "other"}):
                    self.assertEqual(request(body)[0], 400)
                restart.assert_not_called()
                code, body = request({"context_length": 8192})
                self.assertEqual(code, 200)
                self.assertEqual(body, {"status": "ready", "context_length": 8192, "persisted": False})
                self.assertEqual(restart.call_args.args[1]["CTX_SIZE"], "8192")
                restored = Mock()
                restored._llama_launch_settings = {"context_length": 4096}
                restart.side_effect = agent.NativeLlamaRestartError("restored", restored)
                code, body = request({"context_length": 8192})
                self.assertEqual(code, 409)
                self.assertTrue(body["restored"])
                self.assertEqual(body["context_length"], 4096)
                restart.side_effect = OSError("private diagnostic")
                code, body = request({"context_length": 8192})
                self.assertEqual(code, 503)
                self.assertNotIn("private diagnostic", json.dumps(body))
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)

    @unittest.skipUnless(sys.platform == "win32", "Native Windows startup integration")
    def test_starts_without_docker_and_blocks_unported_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / ".env").write_text("ODS_AGENT_KEY=test-native-key\n", encoding="utf-8")
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            environment = dict(os.environ, PATH="")
            process = subprocess.Popen(
                [sys.executable, "-B", str(SOURCE / "bin/ods-host-agent.py"),
                 "--native-windows", "--install-dir", directory, "--port", str(port)],
                env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            try:
                origin = f"http://127.0.0.1:{port}"
                for _ in range(50):
                    try:
                        with urllib.request.urlopen(origin + "/health", timeout=1) as response:
                            health = json.load(response)
                        break
                    except OSError:
                        if process.poll() is not None:
                            self.fail(process.communicate()[1].decode(errors="replace"))
                        time.sleep(0.1)
                else:
                    self.fail("Native server did not start")
                self.assertEqual(health["mode"], "native-windows")
                self.assertEqual(health["capabilities"], ["native-context"])
                for headers, expected in (({}, 401), ({"Authorization": "Bearer test-native-key"}, 501)):
                    request = urllib.request.Request(origin + "/v1/model/activate", data=b"{}", headers=headers)
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(request, timeout=2)
                    self.assertEqual(error.exception.code, expected)
            finally:
                if process.poll() is None:
                    process.terminate()
                process.communicate(timeout=5)
            legacy = subprocess.run(
                [sys.executable, "-B", str(SOURCE / "bin/ods-host-agent.py"),
                 "--install-dir", directory, "--port", str(port)],
                env=environment, capture_output=True, timeout=5,
            )
            self.assertNotEqual(legacy.returncode, 0)
            self.assertIn(b"docker not found in PATH", legacy.stderr)


class NativeLaunchArgumentsTests(unittest.TestCase):
    def test_opt_in_routes_restart_and_retains_restored_session(self):
        agent = bridge.load_host_agent()
        env = dict(ODS_NATIVE_HOST_EXE="C:/ods/ods-native.exe",
                   ODS_NATIVE_LLAMA_EXE="C:/ods/llama-server.exe",
                   ODS_NATIVE_API_KEY_FILE="C:/private/key", GPU_BACKEND="nvidia",
                   GGUF_FILE="Qwen.gguf", CTX_SIZE="4096", N_GPU_LAYERS="99",
                   AMD_INFERENCE_LOCATION="host", AMD_INFERENCE_RUNTIME="llama-server")
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            with patch.object(agent.platform, "system", return_value="Windows"), \
                    patch.object(agent, "_active_model_directory", return_value=Path(directory)), \
                    patch.object(agent._model_stores, "registered_runtime_profile", return_value=None), \
                    patch.object(agent.socket, "socket"), \
                    patch.object(agent, "_start_windows_native_llama") as start, \
                    patch.object(agent, "_restart_windows_native_llama") as restart, \
                    patch.object(agent.subprocess, "run") as shell:
                self.assertTrue(agent._is_windows_host_llama_server(env))
                agent._restart_windows_native_llama_server(env_path, env)
                first = start.return_value
                agent._restart_windows_native_llama_server(env_path, env | {"CTX_SIZE": "8192"})
                self.assertIs(restart.call_args.args[0], first)
                self.assertEqual(restart.call_args.kwargs["context_length"], 8192)
                restored = Mock()
                restart.side_effect = agent.NativeLlamaRestartError("restored", restored)
                with self.assertRaises(agent.NativeLlamaRestartError):
                    agent._restart_windows_native_llama_server(env_path, env)
                self.assertIs(agent._WINDOWS_NATIVE_SESSIONS[env_path.parent.resolve()], restored)
                shell.assert_not_called()
                with self.assertRaises(ValueError):
                    agent._restart_windows_native_llama_server(env_path, env | {"LLAMA_ARG_FLASH_ATTN": "on"})

    @classmethod
    def setUpClass(cls):
        # The host agent adds its bin directory for shared Python imports.
        bridge.load_host_agent()
        from native_windows_runtime import build_llama_arguments
        cls.build = staticmethod(build_llama_arguments)

    def test_basic_cpu_and_cuda_contract(self):
        with tempfile.TemporaryDirectory(prefix="ODS model ") as directory:
            model = Path(directory) / "Qwen.gguf"
            key = Path(directory) / "api key"
            model.write_bytes(b"fixture")
            key.write_text("private-key-value", encoding="ascii")
            options = dict(model=model, api_key_file=key, port=18080,
                           context_length=4096, gpu_layers=99)
            cuda = self.build(**options, backend="cuda")
            cpu = self.build(**options, backend="cpu")
            self.assertEqual(cuda[cuda.index("--model") + 1], str(model))
            self.assertEqual(cuda[cuda.index("--host") + 1], "127.0.0.1")
            self.assertEqual(cuda[cuda.index("--parallel") + 1], "1")
            self.assertEqual(cuda[cuda.index("--n-gpu-layers") + 1], "99")
            self.assertEqual(cpu[cpu.index("--n-gpu-layers") + 1], "0")
            self.assertEqual(cuda[-2:], ["--fit", "off"])
            self.assertNotIn("--fit", cpu)
            self.assertNotIn("private-key-value", cuda)
            self.assertEqual(key.read_text(), "private-key-value")
            for changes in ({"port": 0}, {"context_length": -1},
                            {"gpu_layers": -1}, {"backend": "vulkan"},
                            {"model": Path("relative.gguf")},
                            {"api_key_file": Path(directory) / "missing"}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    self.build(**(options | {"backend": "cuda"} | changes))

    def test_agent_validates_before_starting_the_runtime(self):
        agent = bridge.load_host_agent()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            host, executable, model, key = [root / name for name in
                                            ("ods-native.exe", "llama-server.exe", "Qwen.gguf", "key")]
            for path in (host, executable, model):
                path.write_bytes(b"fixture")
            secret = "ab" * 32
            key.write_bytes(secret.encode("ascii"))
            options = dict(host=host, executable=executable, model=model,
                           api_key_file=key, api_key=secret, log=root / "runtime.log",
                           port=18080, context_length=4096, gpu_layers=99, backend="cuda")
            with patch.object(agent.platform, "system", return_value="Windows"), \
                    patch.object(agent, "_start_windows_native_runtime") as start, \
                    patch.object(agent, "_wait_for_model_readiness", return_value={
                        "contextLength": 4096, "contextVerified": True}) as wait:
                start.return_value.poll.return_value = None
                runtime = agent._start_windows_native_llama(**options)
                self.assertIs(runtime, start.return_value)
                arguments = start.call_args.args[2]
                self.assertIn(str(key), arguments)
                self.assertNotIn(secret, arguments)
                self.assertEqual(wait.call_args.args[0]["CTX_SIZE"], "4096")
                self.assertEqual(wait.call_args.args[0]["LLAMA_SERVER_API_KEY"], secret)
                self.assertTrue(wait.call_args.kwargs["require_exact_context"])
                runtime.stop.assert_not_called()
                for proof in ({}, OSError("proof transport failed"), KeyboardInterrupt()):
                    runtime.stop.reset_mock()
                    wait.side_effect = proof if isinstance(proof, BaseException) else None
                    wait.return_value = proof
                    with self.subTest(proof=type(proof).__name__), self.assertRaises(
                            (RuntimeError, OSError, KeyboardInterrupt)):
                        agent._start_windows_native_llama(**options)
                    runtime.stop.assert_called_once()
                wait.side_effect = None
                wait.return_value = {"contextLength": 4096}
                runtime.poll.return_value = 1
                runtime.stop.reset_mock()
                with self.assertRaises(RuntimeError):
                    agent._start_windows_native_llama(**options)
                runtime.stop.assert_called_once()
                # Restart validates first, then stops, starts and proves in order.
                previous = Mock()
                previous._llama_launch_settings = options.copy()
                previous.poll.return_value = None
                events = []
                def stop_old():
                    events.append("stop-old")
                    previous.poll.return_value = 130
                previous.stop.side_effect = stop_old
                start.side_effect = lambda *args: (events.append("start-new") or runtime)
                runtime.poll.return_value = None
                wait.side_effect = lambda *args, **kwargs: (events.append("prove") or {"contextLength": 8192})
                restarted = agent._restart_windows_native_llama(
                    previous, **(options | {"context_length": 8192}))
                self.assertIs(restarted, runtime)
                self.assertEqual(events, ["stop-old", "start-new", "prove"])
                self.assertEqual(start.call_args.args[2][
                    start.call_args.args[2].index("--ctx-size") + 1], "8192")
                previous.stop.reset_mock()
                previous.poll.return_value = None
                start.reset_mock()
                with self.assertRaises(ValueError):
                    agent._restart_windows_native_llama(previous, **(options | {"port": 0}))
                previous.stop.assert_not_called()
                start.assert_not_called()
                previous.stop.side_effect = OSError("stop failed")
                with self.assertRaises(OSError):
                    agent._restart_windows_native_llama(previous, **options)
                start.assert_not_called()
                previous.stop.side_effect = None
                previous.poll.return_value = None
                with self.assertRaises(RuntimeError):
                    agent._restart_windows_native_llama(previous, **options)
                start.assert_not_called()
                previous.stop.side_effect = stop_old
                wait.side_effect = None
                wait.return_value = {}
                runtime.stop.reset_mock()
                with self.assertRaises(RuntimeError):
                    agent._restart_windows_native_llama(previous, **options)
                self.assertEqual(runtime.stop.call_count, 2)
                wait.side_effect = [{}, {"contextLength": 4096}]
                runtime.stop.reset_mock()
                with self.assertRaises(agent.NativeLlamaRestartError) as failure:
                    agent._restart_windows_native_llama(previous, **(options | {"context_length": 8192}))
                self.assertIs(failure.exception.restored_runtime, runtime)
                runtime.stop.assert_called_once()
                self.assertEqual(start.call_args.args[2][
                    start.call_args.args[2].index("--ctx-size") + 1], "4096")
                start.side_effect = None
                for change in ({"api_key": "invalid"}, {"api_key": "cd" * 32},
                               {"host": root / "missing.exe"}, {"log": key}):
                    start.reset_mock()
                    with self.subTest(change=change), self.assertRaises(ValueError):
                        agent._start_windows_native_llama(**(options | change))
                    start.assert_not_called()
            self.assertEqual(key.read_bytes(), secret.encode("ascii"))


if __name__ == "__main__":
    unittest.main()
