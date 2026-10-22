$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path ".venv/Scripts/python.exe")) {
    py -3.13 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the environment. Install Python 3.13 (64-bit) with the py launcher." }
}
& .venv/Scripts/python.exe -m pip install -e .
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed. See the error above." }
& .venv/Scripts/python.exe main.py
if ($LASTEXITCODE -ne 0) { throw "Director Control exited with an error. See the error above." }
