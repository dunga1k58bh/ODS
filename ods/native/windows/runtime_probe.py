"""Read-only bridge to the host agent's existing llama-server proof contract."""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
from pathlib import Path
import signal
import sys
import threading


def load_host_agent():
    source = Path(__file__).resolve().parents[2] / "bin" / "ods-host-agent.py"
    spec = importlib.util.spec_from_file_location("_ods_native_probe_agent", source)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load ODS host agent: {source}")
    agent = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = agent
    spec.loader.exec_module(agent)
    return agent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not args.model.strip():
        parser.error("a port in 1..65535 and a nonempty model are required")

    cancel = threading.Event()
    signal.signal(signal.SIGINT, lambda _signal, _frame: cancel.set())
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    agent = load_host_agent()
    # These are proof transport settings, not a hardware/backend selection.
    env = {"GPU_BACKEND": "cpu", "OLLAMA_PORT": str(args.port)}
    if agent._runtime_endpoint(env) != (f"http://127.0.0.1:{args.port}", "direct"):
        raise ValueError("Native probe requires the direct Windows loopback transport")

    model = Path(args.model).name
    diagnosis = {}
    proof = agent._wait_for_model_readiness(
        env, model_id=model, gguf_file=model, llm_model_name=model,
        attempts=120, initial_delay=0, interval=1,
        cancel_event=cancel, diagnosis=diagnosis, return_proof=True,
    )
    print(json.dumps({"ok": bool(proof), "proof": proof,
                      "detail": "" if proof else diagnosis.get("reason", "")}), flush=True)
    return 130 if cancel.is_set() else (0 if proof else 1)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, ImportError) as error:
        print(f"ODS runtime proof failed: {error}", file=sys.stderr)
        sys.exit(1)
