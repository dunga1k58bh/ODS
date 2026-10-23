#pragma once

#include "../base/child_process.hpp"

#include <chrono>
#include <cstdint>

// Delegates ODS readiness/identity/completion policy to the existing Python code.
class PythonRuntimeProbe
{
  public:
    enum class Result { Ready, TimedOut, ProcessExited, Cancelled, Failed };

    PythonRuntimeProbe(std::filesystem::path python, std::filesystem::path script,
                       std::uint16_t port, std::filesystem::path model);
    [[nodiscard]] Result WaitUntilReady(const ChildProcess& runtime, HANDLE stop_event,
                                        std::chrono::seconds timeout = std::chrono::seconds{
                                            120}) const;

  private:
    std::filesystem::path python_;
    std::filesystem::path script_;
    std::uint16_t port_;
    std::filesystem::path model_;
};
