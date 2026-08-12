# Opensource demo up (Windows PowerShell)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
New-Item -ItemType Directory -Force -Path ".demo" | Out-Null

docker compose -f deploy/docker-compose.demo.yml up -d --build
Write-Host "Waiting for API health…"
$ok = $false
for ($i = 0; $i -lt 90; $i++) {
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 5
    if ($r.StatusCode -eq 200) { $ok = $true; break }
  } catch { Start-Sleep -Seconds 2 }
}
if (-not $ok) {
  Write-Host "ERROR: API not healthy. Run: docker compose -f deploy/docker-compose.demo.yml logs api"
  exit 1
}
Write-Host "DEMO_READY"
Write-Host "UI http://localhost:8080  API http://127.0.0.1:8000  admin/demo123456"
