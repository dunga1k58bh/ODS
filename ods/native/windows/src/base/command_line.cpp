#include "command_line.hpp"

#include <array>

namespace
{
constexpr std::wstring_view kSwitchTerminator = L"--";
// Match the longest prefix first.
constexpr std::array<std::wstring_view, 3> kSwitchPrefixes{L"--", L"-", L"/"};
constexpr wchar_t kSwitchValueSeparator = L'=';
constexpr wchar_t kQuote = L'"';
constexpr wchar_t kBackslash = L'\\';

std::wstring QuoteArgument(std::wstring_view argument)
{
    std::wstring result(1, kQuote);
    std::size_t backslashes = 0;
    for (const auto character : argument) {
        if (character == kBackslash) {
            ++backslashes;
            continue;
        }
        // Backslashes before a quote must be doubled, then escape the quote.
        result.append(character == kQuote ? backslashes * 2 + 1 : backslashes, kBackslash);
        result += character;
        backslashes = 0;
    }
    // Double trailing backslashes so they do not escape the closing quote.
    result.append(backslashes * 2, kBackslash);
    result += kQuote;
    return result;
}
} // namespace

CommandLine::CommandLine(int argc, const wchar_t* const argv[])
{
    InitFromArgv(argc, argv);
}

CommandLine::CommandLine(std::wstring_view program) : program_(program) {}

void CommandLine::AppendArgNative(std::wstring_view argument)
{
    raw_arguments_.emplace_back(argument);
    arguments_.emplace_back(argument);
}

std::wstring CommandLine::GetCommandLineString() const
{
    // argv[0] uses special CRT parsing; a valid Windows executable path cannot
    // contain quotes or end in a directory separator.
    std::wstring result = L"\"" + program_ + L"\"";
    for (const auto& argument : raw_arguments_) {
        result += L' ';
        result += QuoteArgument(argument);
    }
    return result;
}

void CommandLine::InitFromArgv(int argc, const wchar_t* const argv[])
{
    if (argc > 0) {
        program_ = argv[0];
    }
    bool parse_switches = true;
    for (int index = 1; index < argc; ++index) {
        const std::wstring_view argument{argv[index]};
        raw_arguments_.emplace_back(argument);
        if (parse_switches && argument == kSwitchTerminator) {
            parse_switches = false;
            continue;
        }
        if (parse_switches && ParseSwitch(argument)) {
            continue;
        }
        arguments_.emplace_back(argument);
    }
}

bool CommandLine::ParseSwitch(std::wstring_view argument)
{
    for (const auto prefix : kSwitchPrefixes) {
        if (!argument.starts_with(prefix) || argument.size() <= prefix.size()) {
            continue;
        }
        const auto switch_text = argument.substr(prefix.size());
        const auto separator = switch_text.find(kSwitchValueSeparator);
        const auto name = switch_text.substr(0, separator);
        const auto value = separator == std::wstring_view::npos ? std::wstring_view{}
                                                                : switch_text.substr(separator + 1);
        switches_.insert_or_assign(std::wstring{name}, std::wstring{value});
        return true;
    }
    return false;
}

const std::wstring& CommandLine::GetProgram() const noexcept
{
    return program_;
}

bool CommandLine::HasSwitch(std::wstring_view name) const
{
    return switches_.contains(name);
}

std::wstring CommandLine::GetSwitchValueNative(std::wstring_view name) const
{
    const auto found = switches_.find(name);
    return found == switches_.end() ? std::wstring{} : found->second;
}

const std::vector<std::wstring>& CommandLine::GetArgs() const noexcept
{
    return arguments_;
}

const std::map<std::wstring, std::wstring, std::less<>>& CommandLine::GetSwitches() const noexcept
{
    return switches_;
}
