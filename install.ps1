# SysPulse Windows Installer (https://github.com/P374R/syspulse-cli)
$ErrorActionPreference = "Stop"

Write-Host "==> Installing SysPulse CLI for Windows..." -ForegroundColor Cyan

$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\SysPulse"
if (!(Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

$ExePath = Join-Path $InstallDir "syspulse.exe"
$ReleaseUrl = "https://github.com/P374R/syspulse-cli/releases/latest/download/syspulse-windows-x64.exe"

try {
    Write-Host "==> Downloading latest SysPulse executable..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $ReleaseUrl -OutFile $ExePath -UseBasicParsing
} catch {
    Write-Host "==> Release binary not found yet, falling back to python script runner..." -ForegroundColor Yellow
    $ScriptPath = Join-Path $InstallDir "main.py"
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/P374R/syspulse-cli/main/main.py" -OutFile $ScriptPath -UseBasicParsing
    
    # Create syspulse.cmd launcher
    $CmdPath = Join-Path $InstallDir "syspulse.cmd"
    Set-Content -Path $CmdPath -Value "@echo off`r`npython `"$ScriptPath`" %*"
    
    $CmdPath2 = Join-Path $InstallDir "syspulse-cli.cmd"
    Set-Content -Path $CmdPath2 -Value "@echo off`r`npython `"$ScriptPath`" %*"
}

# Add to User PATH if missing
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath -notlike "*$InstallDir*") {
    Write-Host "==> Adding $InstallDir to user PATH..." -ForegroundColor Cyan
    [Environment]::SetEnvironmentVariable("Path", "$UserPath;$InstallDir", "User")
    $env:PATH += ";$InstallDir"
}

Write-Host "==> SysPulse CLI successfully installed!" -ForegroundColor Green
Write-Host "    Type 'syspulse' to launch." -ForegroundColor White

