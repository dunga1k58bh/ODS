"""Exercise the native bridge against the real host-agent proof implementation."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
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


if __name__ == "__main__":
    unittest.main()
