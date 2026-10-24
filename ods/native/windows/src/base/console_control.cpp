#include "console_control.hpp"
#include "logging.hpp"

#include <mutex>
#include <stdexcept>
#include <system_error>

namespace
{
std::mutex handler_mutex;
HANDLE handler_event = nullptr;

BOOL WINAPI HandleConsoleControl(DWORD type)
{
    if (type != CTRL_C_EVENT && type != CTRL_BREAK_EVENT) {
        return FALSE;
    }
    const std::lock_guard lock{handler_mutex};
    return handler_event && SetEvent(handler_event);
}
} // namespace

ConsoleControl::ConsoleControl(const std::wstring& request_event_name)
{
    const std::lock_guard lock{handler_mutex};
    if (handler_event) {
        throw std::system_error(ERROR_ALREADY_EXISTS, std::system_category(),
                                "Console handler already registered");
    }
    if (!request_event_name.empty()) {
        // Never broadcast a programmatic Ctrl+C into the caller's shared console.
        DWORD console_process = 0;
        if (GetConsoleProcessList(&console_process, 1) != 1 ||
            console_process != GetCurrentProcessId()) {
            throw std::runtime_error(
                "--stop-event requires a private console (CREATE_NEW_CONSOLE)");
        }
        request_event_.reset(OpenEventW(SYNCHRONIZE, FALSE, request_event_name.c_str()));
        if (!request_event_) {
            throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                    "Opening controller stop event failed");
        }
        finished_event_.reset(CreateEventW(nullptr, TRUE, FALSE, nullptr));
        if (!finished_event_) {
            throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                    "Creating stop listener completion event failed");
        }
    }
    // Hosts launched by another process may inherit the ignore-Ctrl+C flag.
    // Restore normal delivery before launching children in this console.
    if (!SetConsoleCtrlHandler(nullptr, FALSE)) {
        throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                "Enabling console Ctrl+C delivery failed");
    }
    stop_event_.reset(CreateEventW(nullptr, TRUE, FALSE, nullptr));
    if (!stop_event_) {
        throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                "Creating console stop event failed");
    }
    if (!SetConsoleCtrlHandler(HandleConsoleControl, TRUE)) {
        const auto error = GetLastError();
        throw std::system_error(static_cast<int>(error), std::system_category(),
                                "Registering console handler failed");
    }
    handler_event = stop_event_.get();
}

ConsoleControl::~ConsoleControl()
{
    if (listener_.joinable()) {
        SetEvent(finished_event_.get());
        listener_.join();
    }
    SetConsoleCtrlHandler(HandleConsoleControl, FALSE);
    const std::lock_guard lock{handler_mutex};
    handler_event = nullptr;
}

HANDLE ConsoleControl::GetStopEvent() const noexcept
{
    return stop_event_.get();
}

void ConsoleControl::StartStopListener()
{
    if (!request_event_) {
        return;
    }
    if (listener_.joinable()) {
        throw std::logic_error("Stop listener already started");
    }
    listener_ = std::jthread{[this] {
        const HANDLE events[]{finished_event_.get(), request_event_.get()};
        const auto result = WaitForMultipleObjects(2, events, FALSE, INFINITE);
        if (result == WAIT_OBJECT_0) {
            return;
        }
        if (result == WAIT_FAILED) {
            VLOG(0) << "Controller stop wait failed: " << GetLastError();
        } else if (!GenerateConsoleCtrlEvent(CTRL_C_EVENT, 0)) {
            VLOG(0) << "Sending shutdown Ctrl+C failed: " << GetLastError();
        }
        // Also signal directly: if delivery failed, Wait still reaches its
        // bounded grace period and Job Object termination fallback.
        SetEvent(stop_event_.get());
    }};
}
