#include "child_process.hpp"
#include "child_output.hpp"
#include "command_line.hpp"
#include "logging.hpp"

#include <windows.h>

#include <optional>
#include <string>
#include <system_error>
#include <utility>

void ChildProcess::HandleCloser::operator()(void* handle) const noexcept
{
    CloseHandle(handle);
}

ChildProcess::ChildProcess(UniqueHandle process, UniqueHandle job) noexcept
    : process_(std::move(process)), job_(std::move(job))
{
}

ChildProcess ChildProcess::Start(const std::filesystem::path& executable,
                                 const std::vector<std::wstring>& arguments,
                                 const std::filesystem::path& log_file)
{
    const auto path = std::filesystem::absolute(executable);
    CommandLine command{path.native()};
    for (const auto& argument : arguments) {
        command.AppendArgNative(argument);
    }
    auto command_line = command.GetCommandLineString();

    UniqueHandle job{CreateJobObjectW(nullptr, nullptr)};
    if (!job) {
        throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                "CreateJobObjectW failed");
    }
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!SetInformationJobObject(job.get(), JobObjectExtendedLimitInformation, &limits,
                                 sizeof(limits))) {
        throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                "Configuring process job failed");
    }

    STARTUPINFOEXW startup{};
    startup.StartupInfo.cb = sizeof(STARTUPINFOW);
    std::optional<ChildOutput> output;
    DWORD creation_flags = CREATE_SUSPENDED;
    if (!log_file.empty()) {
        output.emplace(log_file);
        output->Configure(startup);
        creation_flags |= EXTENDED_STARTUPINFO_PRESENT;
    }
    PROCESS_INFORMATION info{};

    // Suspend until job ownership is established so the child cannot spawn
    // descendants outside our job during startup. Share the console so user
    // Ctrl+C reaches the child's own shutdown handler as well as the host.
    if (!CreateProcessW(path.c_str(), command_line.data(), nullptr, nullptr, output.has_value(),
                        creation_flags, nullptr, nullptr, &startup.StartupInfo, &info)) {
        throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                "CreateProcessW failed");
    }

    // Both handles are released on normal return and exception paths.
    UniqueHandle process{info.hProcess};
    UniqueHandle thread{info.hThread};
    if (!AssignProcessToJobObject(job.get(), process.get())) {
        const auto assignment_error = GetLastError();
        // The suspended process is not owned by the job yet; clean it up directly.
        if (!TerminateProcess(process.get(), ERROR_PROCESS_ABORTED)) {
            throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                    "Cleaning up unassigned child failed");
        }
        throw std::system_error(static_cast<int>(assignment_error), std::system_category(),
                                "AssignProcessToJobObject failed");
    }
    if (ResumeThread(thread.get()) == static_cast<DWORD>(-1)) {
        throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                "Resuming child failed");
    }
    VLOG(1) << "Started child PID " << info.dwProcessId;
    return ChildProcess{std::move(process), std::move(job)};
}

bool ChildProcess::IsRunning() const
{
    const auto result = WaitForSingleObject(process_.get(), 0);
    if (result == WAIT_FAILED) {
        throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                "Checking child process state failed");
    }
    return result == WAIT_TIMEOUT;
}

std::uint32_t ChildProcess::Wait(HANDLE stop_event, DWORD shutdown_timeout_ms) const
{
    if (!process_) {
        throw std::system_error(ERROR_INVALID_HANDLE, std::system_category(),
                                "Cannot wait without an owned process");
    }

    constexpr DWORD kInterruptedExitCode = 130;
    // Windows chooses the first signaled handle. A pending stop takes priority
    // even if the child completed its graceful shutdown before we began waiting.
    const HANDLE handles[]{stop_event ? stop_event : process_.get(), process_.get()};
    const auto result = WaitForMultipleObjects(stop_event ? 2 : 1, handles, FALSE, INFINITE);
    if (result == WAIT_FAILED) {
        throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                "Waiting for child failed");
    }

    if (stop_event && result == WAIT_OBJECT_0) {
        VLOG(1) << "Console interrupt: waiting up to " << shutdown_timeout_ms
                << " ms for child shutdown";
        const auto shutdown_result = WaitForSingleObject(process_.get(), shutdown_timeout_ms);
        if (shutdown_result == WAIT_OBJECT_0) {
            VLOG(1) << "Child exited during shutdown grace period";
            return kInterruptedExitCode;
        }
        if (shutdown_result == WAIT_FAILED) {
            throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                    "Waiting for graceful child shutdown failed");
        }
        VLOG(1) << "Shutdown timeout: terminating child job";
        if (!TerminateJobObject(job_.get(), kInterruptedExitCode)) {
            throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                    "Terminating child job failed");
        }
        if (WaitForSingleObject(process_.get(), INFINITE) == WAIT_FAILED) {
            throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                    "Waiting for interrupted child failed");
        }
        return kInterruptedExitCode;
    }

    DWORD exit_code{};
    if (!GetExitCodeProcess(process_.get(), &exit_code)) {
        throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                "Reading child exit code failed");
    }
    VLOG(1) << "Child exited with code " << exit_code;
    return exit_code;
}
