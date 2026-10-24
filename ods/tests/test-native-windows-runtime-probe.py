"""Exercise the native bridge against the real host-agent proof implementation."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


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


class NativeLaunchArgumentsTests(unittest.TestCase):
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
                for change in ({"api_key": "invalid"}, {"api_key": "cd" * 32},
                               {"host": root / "missing.exe"}, {"log": key}):
                    start.reset_mock()
                    with self.subTest(change=change), self.assertRaises(ValueError):
                        agent._start_windows_native_llama(**(options | change))
                    start.assert_not_called()
            self.assertEqual(key.read_bytes(), secret.encode("ascii"))


if __name__ == "__main__":
    unittest.main()
