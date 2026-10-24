# Manual RTX/CUDA smoke; leaves the installed ODS configuration unchanged.
[CmdletBinding()]
param(
    [string]$Llama = 'D:\data\llama-server.exe',
    [string]$Model = 'D:\data\Qwen3.5-9B-Q4_K_M.gguf',
    [string]$Python,
    [string]$HostExecutable,
    [ValidateRange(1, 65535)][int]$Port = 18080
)
$ErrorActionPreference = 'Stop'
if (-not $Python) { $Python = Join-Path $PSScriptRoot 'build\python-3.13.17\python.exe' }
if (-not $HostExecutable) { $HostExecutable = Join-Path $PSScriptRoot 'build\debug\ods-native.exe' }
foreach ($path in @($Llama, $Model, $Python, $HostExecutable)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file not found: $path" }
}
& $Python -B (Join-Path $PSScriptRoot 'smoke.py') --host $HostExecutable --llama $Llama --model $Model --port $Port
if ($LASTEXITCODE -ne 0) { throw "Native lifecycle smoke failed (exit $LASTEXITCODE)" }
