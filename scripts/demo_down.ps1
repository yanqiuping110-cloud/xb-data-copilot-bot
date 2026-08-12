# Opensource demo down / reset (Windows PowerShell)
param([switch]$Reset)
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if ($Reset) {
  docker compose -f deploy/docker-compose.demo.yml down -v
  Remove-Item -Force -ErrorAction SilentlyContinue .demo/ready, .demo/last-smoke.log
} else {
  docker compose -f deploy/docker-compose.demo.yml down
}
