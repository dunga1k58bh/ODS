#include "python_runtime_probe.hpp"

#include <stdexcept>
#include <string>
#include <system_error>
#include <utility>

PythonRuntimeProbe::PythonRuntimeProbe(std::filesystem::path python, std::filesystem::path script,
                                       std::uint16_t port, std::filesystem::path model)
    : python_(std::move(python)), script_(std::move(script)), port_(port), model_(std::move(model))
{
    if (!std::filesystem::is_regular_file(python_) || !std::filesystem::is_regular_file(script_)) {
        throw std::runtime_error(
            "Readiness requires a Python executable and the ODS runtime_probe.py helper");
    }
    if (port_ == 0 || model_.empty()) {
        throw std::invalid_argument("Readiness requires a port and an expected model");
    }
}

PythonRuntimeProbe::Result PythonRuntimeProbe::WaitUntilReady(const ChildProcess& runtime,
                                                              HANDLE stop_event,
                                                              std::chrono::seconds timeout) const
{
    // A separate owned job lets cancellation also clean up Python's curl children.
    auto probe =
        ChildProcess::Start(python_, {L"-X", L"utf8", L"-B", script_.wstring(), L"--port",
                                      std::to_wstring(port_), L"--model", model_.wstring()});
    constexpr DWORD kPollIntervalMs = 100;
    const auto deadline = std::chrono::steady_clock::now() + timeout;
    for (;;) {
        if (stop_event) {
            const auto stopped = WaitForSingleObject(stop_event, kPollIntervalMs);
            if (stopped == WAIT_OBJECT_0) {
                return Result::Cancelled;
            }
            if (stopped == WAIT_FAILED) {
                throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                        "Waiting for Python probe cancellation failed");
            }
        } else {
            Sleep(kPollIntervalMs);
        }
        if (!runtime.IsRunning()) {
            return Result::ProcessExited;
        }
        if (std::chrono::steady_clock::now() >= deadline) {
            return Result::TimedOut;
        }
        if (!probe.IsRunning()) {
            return probe.Wait() == 0 ? Result::Ready : Result::Failed;
        }
    }
}
