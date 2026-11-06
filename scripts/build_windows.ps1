param([string]$SourceRoot = (Join-Path $PSScriptRoot '..'), [string]$ISCC = '')
$ErrorActionPreference = 'Stop'
$SourceRoot = (Resolve-Path $SourceRoot).Path
$Packaging = (Resolve-Path (Join-Path $PSScriptRoot '../packaging')).Path
Set-Location $SourceRoot
if (-not $IsWindows -and $env:OS -ne 'Windows_NT') { throw 'Build on Windows x64 with Python 3.13.' }
$Venv = Join-Path $SourceRoot '.build-venv'
$LockHash = (Get-FileHash "$Packaging/requirements-windows.lock" -Algorithm SHA256).Hash
$LockMarker = Join-Path $Venv '.director-lock.sha256'
# A changed lock must not leave removed Qt packages/plugins in a reused build.
if ((Test-Path -LiteralPath $Venv) -and
    (-not (Test-Path -LiteralPath $LockMarker) -or (Get-Content -LiteralPath $LockMarker -Raw).Trim() -ne $LockHash)) {
    $ResolvedVenv = (Resolve-Path -LiteralPath $Venv).Path
    $ExpectedVenv = [IO.Path]::GetFullPath((Join-Path $SourceRoot '.build-venv'))
    if ($ResolvedVenv -ne $ExpectedVenv -or ((Get-Item -LiteralPath $Venv).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Refusing to clean a build environment outside the selected source root.'
    }
    Remove-Item -LiteralPath $ResolvedVenv -Recurse -Force
}
if (-not (Test-Path "$Venv/Scripts/python.exe")) {
    py -3.13 -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 x64 is required.' }
}
$Python = "$Venv/Scripts/python.exe"
& $Python -c "import sys,struct; assert sys.version_info[:2]==(3,13) and struct.calcsize('P')==8"
if ($LASTEXITCODE -ne 0) { throw 'Wrong Python version or architecture.' }
& $Python -m pip install --no-deps -r "$Packaging/requirements-windows.lock"
if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed.' }
& $Python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Incomplete build dependency lock.' }
$LockHash | Set-Content -LiteralPath $LockMarker -Encoding ascii
$Version = (& $Python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])").Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot read version.' }
$env:DIRECTOR_BUILD_ROOT = $SourceRoot
& $Python -m PyInstaller --clean --noconfirm --distpath "$SourceRoot/dist" --workpath "$SourceRoot/build" "$Packaging/director-calendar.spec"
if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
$App = "$SourceRoot/dist/DirectorCalendar"
if (-not (Test-Path "$App/DirectorCalendar.exe")) { throw 'Missing executable.' }
if (-not $ISCC) { $ISCC = "${env:ProgramFiles(x86)}/Inno Setup 6/ISCC.exe" }
if (-not (Test-Path $ISCC)) { throw 'Install Inno Setup 6 or pass -ISCC.' }
# ISCC has no Windows version resource (FileVersion is 0.0.0.0).
$CompilerVersion = (& $ISCC /? | Select-Object -First 3) -join ' '
Write-Host $CompilerVersion
$Output = "$SourceRoot/dist/artifacts"
New-Item -ItemType Directory -Force $Output | Out-Null
& $ISCC "/DAppVersion=$Version" "/DSourceDir=$App" "/DBuildOutput=$Output" "$Packaging/installer.iss"
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
$Setup = "$Output/DirectorCalendar-$Version-Setup-x64.exe"
if (-not (Test-Path $Setup)) { throw 'Missing installer.' }
Compress-Archive -Path $App -DestinationPath "$Output/DirectorCalendar-$Version-portable-x64.zip" -Force
$BundleFiles = Get-ChildItem -LiteralPath $App -Recurse -File
$BundleBytes = ($BundleFiles | Measure-Object -Property Length -Sum).Sum
$SetupBytes = (Get-Item -LiteralPath $Setup).Length
$PortableBytes = (Get-Item -LiteralPath "$Output/DirectorCalendar-$Version-portable-x64.zip").Length
$Sizes = "Bundle bytes: $BundleBytes; Files: $($BundleFiles.Count); Installer bytes: $SetupBytes; Portable bytes: $PortableBytes"
"Python: $(& $Python --version); Inno Setup: $CompilerVersion`n$Sizes`nSource: $(git rev-parse HEAD)" | Set-Content "$Output/build-info.txt"
Write-Host $Sizes
if ($env:GITHUB_STEP_SUMMARY) { "### Distribution size`n`n$Sizes`n" | Add-Content -LiteralPath $env:GITHUB_STEP_SUMMARY }
& $Python -m pip freeze | Set-Content "$Output/build-dependencies.txt"
if ($LASTEXITCODE -ne 0) { throw 'Cannot record dependencies.' }
Get-ChildItem $Output -File | Where-Object Extension -in '.exe','.zip' | ForEach-Object {
    "$((Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower())  $($_.Name)"
} | Set-Content -Encoding ascii "$Output/SHA256SUMS.txt"
Write-Host "Build complete: $Output"
