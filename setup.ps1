# OpsBrain pre-deployment setup — Windows (PowerShell)
# Run as: .\setup.ps1
# Or with flags: .\setup.ps1 --check    (verify existing .env)
#                .\setup.ps1 --start    (setup + start)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║              OpsBrain — Pre-deployment Setup             ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Check Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command python3 -ErrorAction SilentlyContinue
}
if (-not $python) {
    Write-Host "  ✗  Python 3.8+ is required. Install from https://python.org" -ForegroundColor Red
    exit 1
}
$pyVersion = & $python.Source --version 2>&1
Write-Host "  ✓  $pyVersion found" -ForegroundColor Green

# Install minimal setup dependencies
Write-Host "  →  Installing setup dependencies…" -ForegroundColor Cyan
& $python.Source -m pip install anthropic openai boto3 google-cloud-aiplatform azure-identity python-dotenv --quiet 2>$null

# Run the wizard, forwarding all arguments
& $python.Source setup.py @args
