#pragma once

#include <windows.h>

#include <cstdint>
#include <filesystem>
#include <memory>
#include <string>
#include <vector>

// Owns a process and its Job Object. Destruction terminates any remaining
// processes in the job, including descendants.
class ChildProcess
{
  public:
    // Starts with literal arguments and returns without waiting for termination.
    // Windows launch/wait failures throw std::system_error.
    [[nodiscard]] static ChildProcess Start(const std::filesystem::path& executable,
                                            const std::vector<std::wstring>& arguments = {},
                                            const std::filesystem::path& log_file = {});

    ChildProcess(const ChildProcess&) = delete;
    ChildProcess& operator=(const ChildProcess&) = delete;
    ChildProcess(ChildProcess&&) noexcept = default;
    ChildProcess& operator=(ChildProcess&&) noexcept = default;
    ~ChildProcess() = default;

    [[nodiscard]] bool IsRunning() const;

    // Blocks until termination. A moved-from object has no process to wait for.
    // The console event is delivered to both host and child. On stop_event,
    // allow the child time to handle it, then force job termination if needed.
    // A handled stop request returns 130, including after a graceful child exit.
    [[nodiscard]] std::uint32_t Wait(HANDLE stop_event = nullptr,
                                     DWORD shutdown_timeout_ms = 5000) const;

  private:
    struct HandleCloser {
        void operator()(void* handle) const noexcept;
    };
    using UniqueHandle = std::unique_ptr<void, HandleCloser>;

    ChildProcess(UniqueHandle process, UniqueHandle job) noexcept;

    UniqueHandle process_;
    UniqueHandle job_;
};
