# ODS Native Windows

Initial C++ CLI for foreground executable launch. It does not yet manage an
ODS installation or model runtime.

## Build

Requires CMake 3.25+, a 64-bit C++20 compiler, and a Windows SDK.
For MSVC with Ninja, use an x64 Visual Studio Developer PowerShell.

From the repository root:

```powershell
cmake -S ods/native/windows -B ods/native/windows/build/debug -G Ninja -DCMAKE_BUILD_TYPE=Debug
cmake --build ods/native/windows/build/debug
& ./ods/native/windows/build/debug/ods-native.exe --help
```

For a Release build, use a separate `build/release` directory and
`-DCMAKE_BUILD_TYPE=Release`. Build tools are developer dependencies;
end-user runtime packaging will be addressed separately.

## Run an executable

```powershell
& ./ods/native/windows/build/debug/ods-native.exe run 'C:\path to\program.exe'
$LASTEXITCODE
```

`base/command_line.hpp` and `.cpp` define `CommandLine`, which owns the Unicode
program name, switches, and positional arguments from `wmain`. Switch prefixes
are `--`, `-`, and `/`; values use `=`. Names are case-sensitive and queried
without the prefix. Repeated switches keep the last value; `--` ends switch
parsing. `GetProgram()`, `HasSwitch()`, `GetSwitchValueNative()`, `GetSwitches()`,
and `GetArgs()` expose the parsed data. It uses arguments already parsed by the
C++ runtime; it does not reparse or quote a raw Windows command line. There is
no singleton or command-line builder. To pass a path beginning with a switch
prefix, use `ods-native run -- <executable>`.
`main.cpp` validates the application command, calls
`ChildProcess::Start()`, then calls `Wait()` to return the child's exit code.
`base/child_process.hpp` defines the move-only owner; its `.cpp` implements
Windows launch and wait operations. Starting returns without waiting for exit.
Moving transfers ownership; copying is prohibited. Windows API failures are
reported on stderr. Process and thread handles are closed automatically,
including on errors. Destruction closes the process handle without terminating
the child; calling `Wait()` on a moved-from object reports an invalid handle.

Reusable helpers live in `src/base/`. Classes currently use the global namespace.

This first slice accepts no child arguments and inherits the current working
directory and environment. It does not capture output or implement Job Object
ownership or Ctrl+C cleanup. Use a short-lived executable for now.

## Editor support

CMake exports `compile_commands.json` for Ninja builds. The module's `.clangd`
configuration reads it from `build/debug`, including the C++20 setting and
Windows definitions. Run the Debug configure command above before editing.
Use a clangd version compatible with your installed MSVC headers; the current
Insiders toolchain requires clangd 20 or newer. Restart the clangd language
server if existing diagnostics remain after configuring.

### C++ formatting

Use `PascalCase` for types and functions, `snake_case` for local variables and
parameters, and a trailing underscore for private data members (`process_`).
Keep required entrypoint names (`wmain`), operators, and external API names
unchanged. Naming is a code convention; clang-format only controls layout.

`.clang-format` defines the style for all C++ files in this module: LLVM-based,
four spaces, a 100-column limit, and opening braces on a new line for functions
and classes. clangd uses this file when the editor requests formatting.

In VS Code, select `llvm-vs-code-extensions.vscode-clangd` as the default formatter
for C++ and enable format on save if desired. `.clangd` configures language
analysis; `.clang-format` configures layout.

With `clang-format` on PATH, run from the repository root:

```powershell
$cppFiles = Get-ChildItem ods/native/windows/src -Recurse -File -Include *.cpp,*.hpp
clang-format -i --style=file $cppFiles.FullName
clang-format --dry-run --Werror --style=file $cppFiles.FullName
```
