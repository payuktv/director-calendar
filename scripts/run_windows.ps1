$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path ".venv/Scripts/python.exe")) {
    py -3.14 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the environment. Install Python 3.14.10 (64-bit) with the py launcher." }
}
# Never silently reuse a 3.13 development environment after upgrading sources.
& .venv/Scripts/python.exe -c "import platform,struct; assert platform.python_version()=='3.14.10' and struct.calcsize('P')==8"
if ($LASTEXITCODE -ne 0) { throw "Recreate .venv with Python 3.14.10 x64; this script does not delete existing environments." }
& .venv/Scripts/python.exe -m pip install --require-hashes --only-binary=:all: --no-deps -r packaging/build-tools.lock
if ($LASTEXITCODE -ne 0) { throw "Verified pip bootstrap failed." }
& .venv/Scripts/python.exe -m pip install "setuptools==84.2.1" -e .
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed. See the error above." }
& .venv/Scripts/python.exe scripts/prepare_expat.py .build-expat
if ($LASTEXITCODE -ne 0) { throw "Patched XML runtime preparation failed. MSVC C++ build tools are required." }
& .venv/Scripts/python.exe scripts/prepare_sqlite.py .build-sqlite
if ($LASTEXITCODE -ne 0) { throw "Patched SQLite preparation failed." }
$env:PYTHONPATH = "$(Join-Path (Get-Location) '.build-expat');$(Join-Path (Get-Location) '.build-sqlite')"
& .venv/Scripts/python.exe main.py
if ($LASTEXITCODE -ne 0) { throw "Director Control exited with an error. See the error above." }
