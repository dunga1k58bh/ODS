"""Manual hardware smoke: real inference, restart and injected-failure rollback.

Requires a Windows llama.cpp runtime and GGUF supplied by the developer;
this hardware check is separate from the mocked CI regressions.
"""

import argparse
import importlib.util
import json
import logging
import os
from pathlib import Path
import secrets
import sys
import tempfile
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--llama", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18080)
    args = parser.parse_args()
    if sys.platform != "win32" or os.environ.get("ODS_HOST_INSTALL_DIR"):
        parser.error("Run from native Windows Python without ODS_HOST_INSTALL_DIR")
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "bin"))
    spec = importlib.util.spec_from_file_location("native_smoke_agent", root / "bin/ods-host-agent.py")
    agent = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = agent
    spec.loader.exec_module(agent)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    with tempfile.TemporaryDirectory(prefix="ods-native-smoke-") as directory:
        install = Path(directory)
        data = install / "data"
        data.mkdir()
        # Register the existing model directory read-only by convention; no
        # model copy, symlink, or modification to the real installation.
        model = args.model.resolve()
        (data / "model-stores.json").write_text(json.dumps({
            "schemaVersion": 1, "stores": [{"id": "smoke", "hostPath": str(model.parent)}],
        }), encoding="utf-8")
        key = secrets.token_hex(32)
        key_file = install / "key"
        key_file.write_bytes(key.encode("ascii"))
        env_path = install / ".env"
        env_path.write_text("# Temporary native smoke installation\n", encoding="utf-8")
        env = dict(
            ODS_NATIVE_HOST_EXE=str(args.host.resolve()),
            ODS_NATIVE_LLAMA_EXE=str(args.llama.resolve()),
            ODS_NATIVE_API_KEY_FILE=str(key_file), LLAMA_SERVER_API_KEY=key,
            GPU_BACKEND="nvidia", AMD_INFERENCE_LOCATION="host",
            AMD_INFERENCE_RUNTIME="llama-server", AMD_INFERENCE_PORT=str(args.port),
            ODS_ACTIVE_MODEL_STORE="smoke", GGUF_FILE=model.name,
            CTX_SIZE="4096", N_GPU_LAYERS="99", LLAMA_REASONING="off",
        )
        agent.INSTALL_DIR = install
        try:
            agent._restart_windows_native_llama_server(env_path, env)
            print("PASS: real model/context/completion at context 4096", flush=True)
            env["CTX_SIZE"] = "8192"
            agent._restart_windows_native_llama_server(env_path, env)
            print("PASS: restart to context 8192", flush=True)
            real_proof = agent._wait_for_model_readiness

            def inject_failure(proof_env, **kwargs):
                if proof_env["CTX_SIZE"] == "16384":
                    raise OSError("Smoke test injected a new-configuration proof failure")
                return real_proof(proof_env, **kwargs)

            with patch.object(agent, "_wait_for_model_readiness", side_effect=inject_failure):
                try:
                    agent._restart_windows_native_llama_server(env_path, env | {"CTX_SIZE": "16384"})
                except agent.NativeLlamaRestartError as error:
                    restored = error.restored_runtime
                    if restored is None or restored.poll() is not None:
                        raise RuntimeError("Rollback did not restore a live session") from error
                    if agent._WINDOWS_NATIVE_SESSIONS[install.resolve()] is not restored:
                        raise RuntimeError("Host agent lost ownership of the restored session")
                else:
                    raise RuntimeError("Injected restart failure was not reported")
            print("PASS: injected failure rolled back to verified context 8192", flush=True)
        except BaseException:
            log = data / "native-llama.log"
            if log.is_file():
                print("\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-30:]).replace(key, "[redacted]"), file=sys.stderr)
            raise
        finally:
            session = agent._WINDOWS_NATIVE_SESSIONS.pop(install.resolve(), None)
            if session is not None:
                session.stop()
        print("PASS: owned session stopped; temporary files removed on exit", flush=True)


if __name__ == "__main__":
    main()
