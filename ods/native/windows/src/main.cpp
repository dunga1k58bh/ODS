#include "base/child_process.hpp"
#include "base/command_line.hpp"
#include "base/console_control.hpp"
#include "base/logging.hpp"
#include "runtime/python_runtime_probe.hpp"

#include <iostream>
#include <optional>
#include <string_view>
#include <system_error>

int wmain(int argc, wchar_t* argv[])
{
    constexpr std::wstring_view kVerbosePrefix = L"--v=";
    constexpr std::wstring_view kChildLogPrefix = L"--child-log=";
    constexpr std::wstring_view kWaitReadyPrefix = L"--wait-ready=";
    constexpr std::wstring_view kExpectModelPrefix = L"--expect-model=";
    constexpr std::wstring_view kPythonPrefix = L"--python=";
    constexpr std::wstring_view kOdsRootPrefix = L"--ods-root=";
    constexpr std::wstring_view kStopEventPrefix = L"--stop-event=";
    constexpr unsigned int kMaxPort = 65535;
    std::filesystem::path child_log;
    std::filesystem::path expected_model;
    std::filesystem::path python;
    std::filesystem::path ods_root;
    std::wstring stop_event_name;
    std::uint16_t readiness_port = 0;
    int command_index = 1;
    while (command_index < argc) {
        const std::wstring_view value{argv[command_index]};
        if (value.starts_with(kStopEventPrefix)) {
            if (value.size() == kStopEventPrefix.size()) {
                std::cerr << "Expected --stop-event=<existing event name> before the command.\n";
                return 1;
            }
            stop_event_name = value.substr(kStopEventPrefix.size());
            ++command_index;
            continue;
        }
        if (value.starts_with(kPythonPrefix) || value.starts_with(kOdsRootPrefix)) {
            const bool is_python = value.starts_with(kPythonPrefix);
            const auto prefix = is_python ? kPythonPrefix : kOdsRootPrefix;
            if (value.size() == prefix.size()) {
                std::cerr << "Expected a nonempty --python=<exe> or --ods-root=<path>.\n";
                return 1;
            }
            (is_python ? python : ods_root) = value.substr(prefix.size());
            ++command_index;
            continue;
        }
        if (value.starts_with(kExpectModelPrefix)) {
            if (value.size() == kExpectModelPrefix.size()) {
                std::cerr << "Expected --expect-model=<path> before the command.\n";
                return 1;
            }
            expected_model = value.substr(kExpectModelPrefix.size());
            ++command_index;
            continue;
        }
        if (value.starts_with(kWaitReadyPrefix)) {
            const auto port_text = value.substr(kWaitReadyPrefix.size());
            unsigned int port = 0;
            bool valid = !port_text.empty() && port_text.size() <= 5;
            if (valid) {
                for (const auto digit : port_text) {
                    if (digit < L'0' || digit > L'9') {
                        valid = false;
                        break;
                    }
                    port = port * 10 + (digit - L'0');
                }
            }
            if (!valid || port == 0 || port > kMaxPort) {
                std::cerr << "Expected --wait-ready=<port 1..65535> before the command.\n";
                return 1;
            }
            readiness_port = static_cast<std::uint16_t>(port);
            ++command_index;
            continue;
        }
        if (value.starts_with(kChildLogPrefix)) {
            if (value.size() == kChildLogPrefix.size()) {
                std::cerr << "Expected --child-log=<path> before the command.\n";
                return 1;
            }
            child_log = value.substr(kChildLogPrefix.size());
            ++command_index;
            continue;
        }
        if (!value.starts_with(kVerbosePrefix)) {
            break;
        }
        if (value.size() != kVerbosePrefix.size() + 1 || value.back() < L'0' ||
            value.back() > L'9') {
            std::cerr << "Expected --v=<0..9> before the command.\n";
            return 1;
        }
        Logger::SetVerboseLevel(value.back() - L'0');
        ++command_index;
    }
    // Everything after the executable belongs to the child, including switches.
    const bool run_command =
        command_index < argc && std::wstring_view{argv[command_index]} == L"run";
    const CommandLine command_line{run_command ? command_index : argc, argv};
    const auto& arguments = command_line.GetArgs();
    const auto& switches = command_line.GetSwitches();

    if (command_line.HasSwitch(L"v") && command_index == 1) {
        std::cerr << "Place --v=<0..9> before the command or --help.\n";
        return 1;
    }
    if (command_line.HasSwitch(L"stop-event") && stop_event_name.empty()) {
        std::cerr << "Place --stop-event=<name> before the command.\n";
        return 1;
    }
    if (command_line.HasSwitch(L"child-log") && child_log.empty()) {
        std::cerr << "Place --child-log=<path> before the command or --help.\n";
        return 1;
    }
    if (command_line.HasSwitch(L"wait-ready") && readiness_port == 0) {
        std::cerr << "Place --wait-ready=<port> before the command or --help.\n";
        return 1;
    }
    if (command_line.HasSwitch(L"expect-model") &&
        (expected_model.empty() || readiness_port == 0)) {
        std::cerr << "--expect-model=<path> requires --wait-ready=<port> before the command.\n";
        return 1;
    }
    if (readiness_port != 0 && (expected_model.empty() || python.empty() || ods_root.empty())) {
        std::cerr << "--wait-ready requires --expect-model=<path>, --python=<exe> and "
                     "--ods-root=<ods directory>.\n";
        return 1;
    }

    const auto option_count = switches.size() - (command_line.HasSwitch(L"v") ? 1 : 0) -
                              (command_line.HasSwitch(L"child-log") ? 1 : 0) -
                              (command_line.HasSwitch(L"wait-ready") ? 1 : 0) -
                              (command_line.HasSwitch(L"expect-model") ? 1 : 0) -
                              (command_line.HasSwitch(L"python") ? 1 : 0) -
                              (command_line.HasSwitch(L"ods-root") ? 1 : 0) -
                              (command_line.HasSwitch(L"stop-event") ? 1 : 0);
    if (!run_command && arguments.empty() &&
        (option_count == 0 || (option_count == 1 && command_line.HasSwitch(L"help") &&
                               command_line.GetSwitchValueNative(L"help").empty()))) {
        std::cout
            << "ODS native Windows\n"
               "Usage: ods-native --help\n"
               "       ods-native [--v=<0..9>] [--child-log=<path>]\n"
               "                  [--wait-ready=<port>] [--expect-model=<path>]\n"
               "                  [--python=<exe>] [--ods-root=<ods directory>]\n"
               "                  [--stop-event=<name>]\n"
               "                  run [--] <executable> [arguments...]\n\n"
               "Readiness runs ODS's existing Python model/completion proof (120-second "
               "deadline).\n"
               "Child log mode appends stdout/stderr to the file; stdin is NUL.\n"
               "Named stop requests require a controller-created event and a private console.\n"
               "Run waits for the executable and returns its exit code.\n"
               "Ctrl+C/Ctrl+Break allow up to 5 seconds for child shutdown,\n"
               "then forcibly stop the remaining process tree.\n";
        return 0;
    }

    const int next_index = command_index + 1;
    const int executable_index = next_index < argc && std::wstring_view{argv[next_index]} == L"--"
                                     ? next_index + 1
                                     : next_index;
    if (run_command && argc > executable_index) {
        try {
            ConsoleControl console_control{stop_event_name};
            std::optional<PythonRuntimeProbe> probe;
            if (readiness_port != 0) {
                probe.emplace(python, ods_root / L"native/windows/runtime_probe.py", readiness_port,
                              expected_model);
            }
            const std::vector<std::wstring> child_arguments{argv + executable_index + 1,
                                                            argv + argc};
            auto process = ChildProcess::Start(argv[executable_index], child_arguments, child_log);
            console_control.StartStopListener();
            if (probe) {
                const auto result = probe->WaitUntilReady(process, console_control.GetStopEvent());
                switch (result) {
                    case PythonRuntimeProbe::Result::Ready:
                        std::cout << "llama-server ready on port " << readiness_port << std::endl;
                        if (!expected_model.empty()) {
                            std::cout << "ODS Python model/completion proof verified" << std::endl;
                        }
                        break;
                    case PythonRuntimeProbe::Result::Failed:
                        std::cerr
                            << "ODS Python model/completion proof failed; stopping child job.\n";
                        return 1;
                    case PythonRuntimeProbe::Result::Cancelled:
                        return static_cast<int>(process.Wait(console_control.GetStopEvent()));
                    case PythonRuntimeProbe::Result::ProcessExited:
                        std::cerr << "Child exited before readiness, code " << process.Wait()
                                  << '\n';
                        return 1;
                    case PythonRuntimeProbe::Result::TimedOut:
                        std::cerr << "Readiness timed out after 120 seconds; stopping child job.\n";
                        return 1;
                }
            }
            return static_cast<int>(process.Wait(console_control.GetStopEvent()));
        } catch (const std::exception& error) {
            std::cerr << "Cannot run executable or verify readiness: " << error.what() << '\n';
            return 1;
        }
    }

    std::cerr << "Unsupported arguments. Use ods-native --help.\n";
    return 1;
}
