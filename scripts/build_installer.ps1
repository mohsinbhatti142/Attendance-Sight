$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$compilerPath = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $compilerPath) {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    $compilerPath = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if (-not $compilerPath) {
    throw "Inno Setup 6 is required. Install it from https://jrsoftware.org/isdl.php, then run this script again."
}

if (-not (Test-Path "dist\Attendance-Sight-1.3.4.exe")) {
    throw "Build dist\Attendance-Sight-1.3.4.exe first by running .\scripts\build_windows.ps1."
}

& $compilerPath "scripts\Attendance-Sight.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed to create the Attendance-Sight installer."
}

Write-Host "Attendance-Sight installer created: $repoRoot\dist\Attendance-Sight-Setup-1.3.4.exe"
