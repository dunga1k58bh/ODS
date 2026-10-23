#pragma once

#include <windows.h>

// Registers one process-wide Ctrl+C/Ctrl+Break handler for this scope.
class ConsoleControl
{
  public:
    ConsoleControl();
    ~ConsoleControl();
    ConsoleControl(const ConsoleControl&) = delete;
    ConsoleControl& operator=(const ConsoleControl&) = delete;

    [[nodiscard]] HANDLE GetStopEvent() const noexcept;

  private:
    HANDLE stop_event_ = nullptr;
};
