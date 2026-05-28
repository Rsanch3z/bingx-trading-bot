# Run as Administrator
# Requires: NSSM on PATH (https://nssm.cc/download)
param(
    [string]$BotDir = "D:\投資專案\bingx-trading-bot",
    [string]$ServiceName = "BingXBot"
)

$PythonPath = Join-Path $BotDir ".venv\Scripts\python.exe"
$LogDir = Join-Path $BotDir "logs"

if (-not (Test-Path $PythonPath)) {
    Write-Error "Python venv not found at $PythonPath. Run: python -m venv .venv"
    exit 1
}

New-Item -ItemType Directory -Force $LogDir | Out-Null

Write-Host "Installing $ServiceName Windows Service..."

nssm install $ServiceName $PythonPath "-m" "src.main"
nssm set $ServiceName AppDirectory $BotDir
nssm set $ServiceName AppRestartDelay 5000
nssm set $ServiceName AppStdout (Join-Path $LogDir "service-stdout.log")
nssm set $ServiceName AppStderr (Join-Path $LogDir "service-stderr.log")
nssm set $ServiceName AppRotateFiles 1
nssm set $ServiceName AppRotateOnline 1
nssm set $ServiceName AppRotateSeconds 86400
nssm set $ServiceName Start SERVICE_AUTO_START

nssm start $ServiceName

Write-Host "Service $ServiceName installed and started."
Write-Host "Check status: nssm status $ServiceName"
Write-Host "View logs: Get-Content $LogDir\service-stdout.log -Wait"
