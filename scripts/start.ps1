# Windows PowerShell: set up everything on first run, then start backend + frontend together.
# Run from the project root:   powershell -ExecutionPolicy Bypass -File scripts\start.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$' -and -not $_.TrimStart().StartsWith('#')) {
    [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim('"').Trim("'"), "Process")
  }
}
$venvPy = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
  Write-Host ">> creating virtual environment (.venv)"
  if (Get-Command py -ErrorAction SilentlyContinue) { py -3 -m venv .venv } else { python -m venv .venv }
}
$marker = ".venv\.deps-installed"
if (-not (Test-Path $marker) -or ((Get-Item requirements.txt).LastWriteTime -gt (Get-Item $marker).LastWriteTime)) {
  Write-Host ">> installing Python dependencies"
  & $venvPy -m pip install --upgrade pip -q
  & $venvPy -m pip install -r requirements.txt
  New-Item -ItemType File -Force $marker | Out-Null
}
if (-not (Test-Path "frontend\node_modules")) {
  Write-Host ">> installing frontend packages"
  Push-Location frontend; npm install; Pop-Location
}
$bp = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8000" }
$fp = if ($env:VITE_PORT) { $env:VITE_PORT } else { "5173" }
$backendPort = (& $venvPy scripts\find_port.py $bp).Trim()
$frontendPort = (& $venvPy scripts\find_port.py $fp).Trim()
$env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$backendPort"
$env:VITE_PORT = $frontendPort

Write-Host ">> starting backend on :$backendPort"
$backend = Start-Process -FilePath $venvPy -WorkingDirectory (Join-Path (Get-Location) "backend") `
  -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port",$backendPort -PassThru -NoNewWindow
try {
  for ($i = 0; $i -lt 60; $i++) {
    try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$backendPort/api/health" -TimeoutSec 1 | Out-Null; break } catch { Start-Sleep -Milliseconds 500 }
  }
  Write-Host ">> backend ready: http://127.0.0.1:$backendPort/docs"
  Write-Host ">> starting frontend: open http://localhost:$frontendPort"
  Push-Location frontend
  npm run dev
  Pop-Location
} finally {
  if ($backend -and -not $backend.HasExited) { Stop-Process -Id $backend.Id -Force }
}
