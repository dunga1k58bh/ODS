#pragma once

#include <map>
#include <string>
#include <string_view>
#include <vector>

// Parses the Unicode argv supplied by wmain. Switch values use '=';
// repeated switches keep the last value, and '--' ends switch parsing.
class CommandLine
{
  public:
    CommandLine(int argc, const wchar_t* const argv[]);
    explicit CommandLine(std::wstring_view program);

    // Appends a literal argument without interpreting switch prefixes.
    void AppendArgNative(std::wstring_view argument);
    // Serializes for the Windows C/C++ runtime argument parsing rules.
    [[nodiscard]] std::wstring GetCommandLineString() const;

    [[nodiscard]] const std::wstring& GetProgram() const noexcept;
    [[nodiscard]] bool HasSwitch(std::wstring_view name) const;
    [[nodiscard]] std::wstring GetSwitchValueNative(std::wstring_view name) const;
    [[nodiscard]] const std::vector<std::wstring>& GetArgs() const noexcept;
    [[nodiscard]] const std::map<std::wstring, std::wstring, std::less<>>&
    GetSwitches() const noexcept;

  private:
    void InitFromArgv(int argc, const wchar_t* const argv[]);
    bool ParseSwitch(std::wstring_view argument);

    std::wstring program_;
    std::map<std::wstring, std::wstring, std::less<>> switches_;
    std::vector<std::wstring> arguments_;
    std::vector<std::wstring> raw_arguments_;
};
