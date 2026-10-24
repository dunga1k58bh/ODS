# Native Windows Plan

## Goal

Run ODS core functionality directly on Windows without Docker or WSL. Use C++ for Windows process management and reuse existing React, Python, and model-management logic.

## Working approach

- Deliver one small, understandable change per prompt rather than an entire milestone at once.
- Normally touch only a few related source files; split work when the diff becomes difficult to explain or review.
- Explain each file's responsibility, the execution flow, and the reason for new abstractions.
- Validate the current change and summarize what works and what remains before moving to the next slice.
- Keep build setup, process launch, process ownership, logging, and readiness as separate implementation steps.

## 1. Baseline and feasibility

- Record the working model, llama.cpp version, launch settings, API behavior, and resource usage.
- Map core services and Linux dependencies; review existing Windows/macOS implementations.
- Prove Windows llama.cpp inference and investigate backend packaging and Pixel sandbox blockers early.
- Define the first supported Windows/GPU configurations and core feature scope.

**Exit:** native streaming chat works; core dependencies and migration blockers are documented.

## 2. C++ runtime host

- Implement process launch, log capture, readiness, controlled shutdown, and crash reporting.
- Manage owned process trees with Windows handles and Job Objects.
- Provide a restricted local control interface and diagnostic CLI: start, stop, status, logs.
- Define per-install ownership, single-instance behavior, and recovery after failure.

**Exit:** manage llama-server using an existing GGUF file without orphaned processes or Docker/WSL.

## 3. Integrate ODS core

- Add a native Windows adapter to the existing Model Switchboard.
- Retain model selection, activation transactions, routing, and rollback in the existing control layer.
- Run the required backend services natively and connect the dashboard.
- Once model switching through the UI is ready and verified, remind the user to remove the temporary `smoke.ps1` and `smoke.py` scripts. Keep the automated regression tests.
- Port Portal/Pixel lifecycle, IPC, and permissions; establish Windows execution isolation before enabling agent tools.

**Exit:** onboarding, model download/switching, streaming chat, and unload/resume work end to end.

## 4. Desktop and distribution

- Add a desktop shell, tray behavior, optional sign-in startup, and visible error recovery.
- Bundle runtime dependencies; separate binaries, private state, models, and logs.
- Implement installation, verified updates, rollback, and uninstall with explicit data-retention choices.

**Exit:** users can install and operate ODS on clean Windows without development tools.

## 5. Extensions and qualification

- Port extensions in batches: search/RAG, voice, images, workflows, and observability.
- Declare native platform support and provide migration from existing WSL/Docker installations.
- Validate supported hardware, reboot/sleep recovery, low memory, interrupted operations, update, and removal.

## Code locations

- `ods/native/windows/`: C++ runtime host, build configuration, tests, and later desktop/packaging code.
- `ods/bin/model_switchboard/`: native Windows adapter and existing runtime contracts.
- `ods/bin/ods-host-agent.py`: control-plane integration; extract modules incrementally as needed.
- `ods/extensions/services/dashboard/` and `dashboard-api/`: focused UI/API integration.
- `ods/installers/windows/`: installer integration alongside the existing installation path.

## First deliverable

A C++ runtime host and CLI that start Windows llama.cpp, capture logs, verify readiness/model identity, and stop the owned process tree. Confirm one streaming completion before adding downloads or a desktop shell.

Implement this deliverable in small slices:

1. Capture the existing inference configuration in `BASELINE.md`.
2. Prepare a matching Windows runtime and verify inference manually.
3. Add a minimal foreground process-launch command.
4. Add process ownership, Job Object cleanup, and Ctrl+C handling.
5. Capture stdout/stderr and report runtime failures.
6. Verify health, model identity, and streaming completion.
