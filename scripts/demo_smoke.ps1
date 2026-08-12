# Opensource demo smoke (Windows PowerShell)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
New-Item -ItemType Directory -Force -Path ".demo" | Out-Null
python scripts/demo_smoke.py --base-url http://127.0.0.1:8000 | Tee-Object -FilePath .demo/last-smoke.log
