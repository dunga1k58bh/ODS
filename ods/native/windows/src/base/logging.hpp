#pragma once

#include <ostream>
#include <sstream>

class Logger
{
  public:
    static void SetVerboseLevel(int level) noexcept;
    [[nodiscard]] static bool IsVerboseEnabled(int level) noexcept;
};

// Buffers one message and writes it to stderr on destruction.
class LogMessage
{
  public:
    LogMessage(int level, const char* file, int line);
    ~LogMessage();
    LogMessage(const LogMessage&) = delete;
    LogMessage& operator=(const LogMessage&) = delete;

    std::ostream& Stream() noexcept;

  private:
    std::ostringstream stream_;
};

class LogMessageVoidify
{
  public:
    void operator&(std::ostream&) const noexcept {}
};

// No local identifiers can shadow the caller. The conditional skips disabled
// stream operands and works inside if/else. Keep the level expression side-effect-free.
#define VLOG(level)                                                                                \
    !Logger::IsVerboseEnabled(level)                                                               \
        ? (void)0                                                                                  \
        : LogMessageVoidify{} & LogMessage((level), __FILE__, __LINE__).Stream()
