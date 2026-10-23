#include "base/child_process.hpp"
#include "base/logging.hpp"
#include "runtime/python_runtime_probe.hpp"

#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string_view>

void Check(bool condition, const char* message)
{
    if (!condition) {
        throw std::runtime_error(message);
    }
}

void CheckLogging()
{
    std::ostringstream output;
    auto* previous = std::cerr.rdbuf(output.rdbuf());
    const int vlog_level = 3;
    int evaluated = 0;
    Logger::SetVerboseLevel(0);
    VLOG(vlog_level) << ++evaluated;
    Logger::SetVerboseLevel(3);
    VLOG(vlog_level) << "caller level=" << vlog_level;
    bool else_taken = false;
    if (false)
        VLOG(vlog_level) << "unreachable";
    else
        else_taken = true;
    std::cerr.rdbuf(previous);
    Check(evaluated == 0, "Disabled VLOG evaluated its stream operand");
    Check(else_taken, "VLOG captured the caller's else branch");
    Check(output.str().find("caller level=3") != std::string::npos,
          "VLOG shadowed the caller's level variable");
}

void CheckStopPriority(const std::filesystem::path& self)
{
    using EventHandle = std::unique_ptr<void, decltype(&CloseHandle)>;
    EventHandle stop{CreateEventW(nullptr, TRUE, TRUE, nullptr), &CloseHandle};
    Check(bool(stop), "Cannot create test stop event");
    auto child = ChildProcess::Start(self, {L"--child-exit"});
    Check(child.Wait() == 0, "Normal child exit code changed");
    Check(child.Wait(stop.get()) == 130, "Completed child masked a pending stop request");
}

int wmain(int argc, wchar_t* argv[])
{
    if (argc == 2 && std::wstring_view{argv[1]} == L"--child-exit") {
        return 0;
    }
    if (argc == 2 && std::wstring_view{argv[1]} == L"--child-sleep") {
        Sleep(10000);
        return 0;
    }
    try {
        Check(argc == 3, "Pass Python executable and UTF-8 probe fixture");
        CheckLogging();
        const auto self = std::filesystem::absolute(argv[0]);
        CheckStopPriority(self);
        auto runtime = ChildProcess::Start(self, {L"--child-sleep"});
        const PythonRuntimeProbe probe{argv[1], argv[2], 18080, L"m\u00f4-h\u00ecnh.gguf"};
        Check(probe.WaitUntilReady(runtime, nullptr) == PythonRuntimeProbe::Result::Ready,
              "Python probe did not preserve UTF-8 model text");
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
