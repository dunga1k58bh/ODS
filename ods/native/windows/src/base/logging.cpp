#include "logging.hpp"

#include <atomic>
#include <iostream>
#include <syncstream>

namespace
{
std::atomic<int> verbose_level{0};
}

void Logger::SetVerboseLevel(int level) noexcept
{
    verbose_level.store(level, std::memory_order_relaxed);
}

bool Logger::IsVerboseEnabled(int level) noexcept
{
    return level >= 0 && level <= verbose_level.load(std::memory_order_relaxed);
}

LogMessage::LogMessage(int level, const char* file, int line)
{
    stream_ << "[V" << level << ' ' << file << ':' << line << "] ";
}

LogMessage::~LogMessage()
{
    std::osyncstream{std::cerr} << stream_.str() << '\n';
}

std::ostream& LogMessage::Stream() noexcept
{
    return stream_;
}
