$ErrorActionPreference = "Stop"

if (-not $IsWindows -and $env:OS -ne "Windows_NT") {
    throw "Attendance-Sight's executable must be built on Windows."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "Install uv first: https://docs.astral.sh/uv/getting-started/installation/"
}

$python = Join-Path $repoRoot ".build-venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    uv venv --python 3.10 .build-venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python 3.10 build environment." }
}

uv pip uninstall --python $python onnxruntime
if ($LASTEXITCODE -ne 0) { throw "Could not remove the CPU-only ONNX Runtime package." }

uv pip install --python $python --index https://pypi.nvidia.com --build-constraint packaging\build-constraints.txt -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Could not install Attendance-Sight's executable build dependencies." }

uv pip install --python $python pyinstaller==6.21.0
if ($LASTEXITCODE -ne 0) { throw "Could not install PyInstaller." }

$providerCheck = & $python -c "import src.core.cuda_setup; import onnxruntime as ort; providers = ort.get_available_providers(); print('ONNX Runtime providers:', providers); assert 'CUDAExecutionProvider' in providers, 'CUDAExecutionProvider is missing from this build environment'"
if ($LASTEXITCODE -ne 0) { throw "The executable build environment does not have CUDAExecutionProvider." }

$icon = Join-Path $repoRoot "build\attendsight.ico"
& $python scripts\create_windows_icon.py --output $icon
if ($LASTEXITCODE -ne 0) { throw "Could not generate the application icon." }

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name Attendance-Sight-1.3.4 `
    --specpath build `
    --icon $icon `
    --add-data "$repoRoot\static;static" `
    --hidden-import aiosqlite `
    --hidden-import webview.platforms.edgechromium `
    --collect-all insightface `
    --collect-all albumentations `
    --collect-all cv2 `
    --collect-all faiss `
    --collect-all onnxruntime `
    --collect-all nvidia.cuda_runtime `
    --collect-all nvidia.cublas `
    --collect-all nvidia.cudnn `
    --collect-all nvidia.cufft `
    --collect-all nvidia.cuda_nvrtc `
    --collect-all nvidia.nvjitlink `
    --collect-all webview `
    run_portal.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed to build Attendance-Sight." }

Write-Host ""
Write-Host "Attendance-Sight executable created: $repoRoot\dist\Attendance-Sight-1.3.4.exe"
Write-Host "The app downloads the official face-model pack on first launch."
