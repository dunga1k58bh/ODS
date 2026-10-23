#include "console_control.hpp"

#include <mutex>
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

ConsoleControl::ConsoleControl()
{
    const std::lock_guard lock{handler_mutex};
    if (handler_event) {
        throw std::system_error(ERROR_ALREADY_EXISTS, std::system_category(),
                                "Console handler already registered");
    }
    // Hosts launched by another process may inherit the ignore-Ctrl+C flag.
    // Restore normal delivery before launching children in this console.
    if (!SetConsoleCtrlHandler(nullptr, FALSE)) {
        throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                "Enabling console Ctrl+C delivery failed");
    }
    stop_event_ = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (!stop_event_) {
        throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                "Creating console stop event failed");
    }
    if (!SetConsoleCtrlHandler(HandleConsoleControl, TRUE)) {
        const auto error = GetLastError();
        CloseHandle(stop_event_);
        throw std::system_error(static_cast<int>(error), std::system_category(),
                                "Registering console handler failed");
    }
    handler_event = stop_event_;
}

ConsoleControl::~ConsoleControl()
{
    SetConsoleCtrlHandler(HandleConsoleControl, FALSE);
    const std::lock_guard lock{handler_mutex};
    handler_event = nullptr;
    CloseHandle(stop_event_);
}

HANDLE ConsoleControl::GetStopEvent() const noexcept
{
    return stop_event_;
}
