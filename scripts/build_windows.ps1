$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path ".venv/Scripts/python.exe")) {
    py -3.13 -m venv .venv
}
& .venv/Scripts/python.exe -m pip install -e .
& .venv/Scripts/pyside6-deploy.exe --mode standalone --force
Write-Host "Сборка подготовлена. Проверьте папку dist/ и запустите exe на Windows."
