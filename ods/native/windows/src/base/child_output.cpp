#include "child_output.hpp"

#include <system_error>

void ChildOutput::HandleCloser::operator()(void* handle) const noexcept
{
    CloseHandle(handle);
}

void ChildOutput::AttributeListCloser::operator()(
    LPPROC_THREAD_ATTRIBUTE_LIST attributes) const noexcept
{
    DeleteProcThreadAttributeList(attributes);
}

ChildOutput::ChildOutput(const std::filesystem::path& log_file)
{
    SECURITY_ATTRIBUTES security{sizeof(security), nullptr, TRUE};
    const auto output =
        CreateFileW(log_file.c_str(), FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
                    &security, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (output == INVALID_HANDLE_VALUE) {
        throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                "Opening child log file failed");
    }
    output_.reset(output);
    const auto input = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                   &security, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (input == INVALID_HANDLE_VALUE) {
        throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                "Opening child NUL input failed");
    }
    input_.reset(input);
    inherited_handles_[0] = output_.get();
    inherited_handles_[1] = input_.get();

    SIZE_T size = 0;
    // The sizing call is expected to fail with ERROR_INSUFFICIENT_BUFFER.
    if (InitializeProcThreadAttributeList(nullptr, 1, 0, &size) ||
        GetLastError() != ERROR_INSUFFICIENT_BUFFER) {
        throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                "Sizing child handle list failed");
    }
    storage_.resize(size);
    auto* attributes = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(storage_.data());
    if (!InitializeProcThreadAttributeList(attributes, 1, 0, &size)) {
        throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                "Initializing child handle list failed");
    }
    attributes_.reset(attributes);
    if (!UpdateProcThreadAttribute(attributes_.get(), 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                                   inherited_handles_, sizeof(inherited_handles_), nullptr,
                                   nullptr)) {
        throw std::system_error(static_cast<int>(GetLastError()), std::system_category(),
                                "Restricting inherited child handles failed");
    }
}

void ChildOutput::Configure(STARTUPINFOEXW& startup) const noexcept
{
    startup.StartupInfo.cb = sizeof(startup);
    startup.StartupInfo.dwFlags |= STARTF_USESTDHANDLES;
    startup.StartupInfo.hStdOutput = output_.get();
    startup.StartupInfo.hStdError = output_.get();
    startup.StartupInfo.hStdInput = input_.get();
    startup.lpAttributeList = attributes_.get();
}
