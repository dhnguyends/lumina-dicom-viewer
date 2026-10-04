param([int]$Port = 8765, [string]$DataDir = '')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$existingPython = Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    if (Test-Path -LiteralPath $existingPython) { $taskPython = $existingPython }
    else { $taskPython = 'python' }
}
if ($DataDir) { & $taskPython server.py --port $Port --data-dir $DataDir }
else { & $taskPython server.py --port $Port }
