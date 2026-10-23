# Inference Baseline

Observed configuration of the existing WSL/Docker installation. This records
the comparison target; it is not proof that the Windows runtime works yet.
Private installation paths and credentials are omitted.

## Runtime and model

| Item | Observed value |
| --- | --- |
| Engine | llama.cpp, CUDA container `server-cuda-b11429` |
| Image digest | `sha256:883915ea20a4b350e98f7284098f4d400c21e9b366e248d397cd42d90602a84c` |
| GPU | NVIDIA GeForce RTX 4060 Ti, 16,380 MiB VRAM |
| Windows NVIDIA driver | 610.88 |
| Model / served alias | `Qwen3.5-9B-Q4_K_M.gguf` |
| Model storage | Bind mount from `<ODS_INSTALL_DIR>/data/models` to `/models` |

## Launch settings

| Argument | Value |
| --- | --- |
| `--model` | `/models/Qwen3.5-9B-Q4_K_M.gguf` |
| `--alias` | `Qwen3.5-9B-Q4_K_M.gguf` |
| `--host` / `--port` | `0.0.0.0` / `8080` inside the container |
| `--n-gpu-layers` | `auto` |
| `--ctx-size` | `65536` |
| `--batch-size` | `2048` |
| `--threads` | `4` |
| `--parallel` | `1` |
| `--metrics` | Enabled |

Relevant environment settings:

```text
LLAMA_ARG_FLASH_ATTN=auto
LLAMA_ARG_CACHE_TYPE_K=f16
LLAMA_ARG_CACHE_TYPE_V=f16
LLAMA_ARG_SPEC_TYPE=ngram-mod
```

## Next comparison

- Obtain an official Windows CUDA build matching `b11429` if available; record
  the actual build and any differences if an exact match is unavailable.
- Reuse the existing GGUF through a Windows-accessible local model path.
- Stop the existing inference runtime before allocating the same GPU for the
  comparison; retain its configuration and model files.
- Bind the manual Windows server to `127.0.0.1` on a separate port, using
  equivalent model settings. Do not change the installed ODS routing yet.
- Compare health, reported model/context, a streaming response, startup time,
  RAM, and VRAM after loading has settled. These measurements remain pending.
