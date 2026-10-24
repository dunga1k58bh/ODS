#pragma once

#include <windows.h>

#include <memory>
#include <string>
#include <thread>

// Registers one process-wide Ctrl+C/Ctrl+Break handler for this scope.
class ConsoleControl
{
  public:
    explicit ConsoleControl(const std::wstring& request_event_name = {});
    ~ConsoleControl();
    ConsoleControl(const ConsoleControl&) = delete;
    ConsoleControl& operator=(const ConsoleControl&) = delete;

    [[nodiscard]] HANDLE GetStopEvent() const noexcept;
    // Call after launching the child. Named requests require a private console.
    void StartStopListener();

  private:
    using UniqueHandle = std::unique_ptr<void, decltype(&CloseHandle)>;
    UniqueHandle stop_event_{nullptr, &CloseHandle};
    UniqueHandle request_event_{nullptr, &CloseHandle};
    UniqueHandle finished_event_{nullptr, &CloseHandle};
    std::jthread listener_;
};
