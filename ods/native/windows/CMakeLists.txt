cmake_minimum_required(VERSION 3.25)

project(ods_native_windows LANGUAGES CXX)

# Let editors use the same compiler flags as the Ninja build.
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(NOT WIN32)
    message(FATAL_ERROR "ODS native Windows must be built with a Windows toolchain.")
endif()

if(NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
    message(FATAL_ERROR "ODS native Windows requires a 64-bit toolchain.")
endif()

set(ODS_NATIVE_SOURCES
    src/base/child_output.cpp
    src/base/child_process.cpp
    src/base/command_line.cpp
    src/base/console_control.cpp
    src/base/logging.cpp
    src/runtime/python_runtime_probe.cpp
)

add_executable(ods-native src/main.cpp ${ODS_NATIVE_SOURCES})
set(ODS_NATIVE_TARGETS ods-native)

option(ODS_NATIVE_BUILD_TESTS "Build native Windows regression tests" OFF)
if(ODS_NATIVE_BUILD_TESTS)
    enable_testing()
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    add_executable(ods-native-regressions tests/regressions.cpp ${ODS_NATIVE_SOURCES})
    target_include_directories(ods-native-regressions PRIVATE src)
    list(APPEND ODS_NATIVE_TARGETS ods-native-regressions)
    add_test(NAME native-regressions COMMAND ods-native-regressions
        "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/probe_utf8.py")
    set_tests_properties(native-regressions PROPERTIES TIMEOUT 20)
    add_test(NAME native-stop-event COMMAND "${Python3_EXECUTABLE}" -B
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/stop_event.py" "$<TARGET_FILE:ods-native>")
    set_tests_properties(native-stop-event PROPERTIES TIMEOUT 30)
    if(MSVC)
        target_compile_options(ods-native-regressions PRIVATE /WX)
    endif()
endif()

foreach(target IN LISTS ODS_NATIVE_TARGETS)
    target_compile_features(${target} PRIVATE cxx_std_20)
    set_target_properties(${target} PROPERTIES CXX_EXTENSIONS OFF)

    target_compile_definitions(${target} PRIVATE
        UNICODE
        _UNICODE
        WIN32_LEAN_AND_MEAN
        NOMINMAX
    )

    if(MSVC)
        target_compile_options(${target} PRIVATE /W4 /permissive- /utf-8)
    endif()
endforeach()
