#pragma once

#include <windows.h>

#include <cstddef>
#include <filesystem>
#include <memory>
#include <vector>

// Startup-only resources: redirect both output streams to an append-only file.
// Log mode gives the child EOF on stdin (NUL), suitable for background runtimes.
class ChildOutput
{
  public:
    explicit ChildOutput(const std::filesystem::path& log_file);
    ChildOutput(const ChildOutput&) = delete;
    ChildOutput& operator=(const ChildOutput&) = delete;
    void Configure(STARTUPINFOEXW& startup) const noexcept;

  private:
    struct HandleCloser {
        void operator()(void* handle) const noexcept;
    };
    struct AttributeListCloser {
        void operator()(LPPROC_THREAD_ATTRIBUTE_LIST attributes) const noexcept;
    };
    using UniqueHandle = std::unique_ptr<void, HandleCloser>;

    UniqueHandle output_;
    UniqueHandle input_;
    HANDLE inherited_handles_[2]{};
    std::vector<std::byte> storage_;
    std::unique_ptr<_PROC_THREAD_ATTRIBUTE_LIST, AttributeListCloser> attributes_;
};
