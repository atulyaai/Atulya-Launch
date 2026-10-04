# Atulya Launch installer for Windows 11 (winget + Caddy + NSSM service).
# Run from an elevated PowerShell prompt.
$ErrorActionPreference = "Stop"

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this script as Administrator."
}
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw "winget is required (App Installer)." }

$RepoDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Prefix  = if ($env:ATULYA_PREFIX) { $env:ATULYA_PREFIX } else { "C:\ProgramData\Atulya\Launch" }
$Port    = if ($env:ATULYA_PORT) { $env:ATULYA_PORT } else { "8443" }

foreach ($id in "Python.Python.3.11", "CaddyServer.Caddy", "NSSM.NSSM") {
    winget install --id $id --exact --silent --accept-package-agreements --accept-source-agreements
}

New-Item -ItemType Directory -Force -Path $Prefix | Out-Null
python -m venv "$Prefix\venv"
& "$Prefix\venv\Scripts\pip.exe" install --upgrade pip
& "$Prefix\venv\Scripts\pip.exe" install -r "$RepoDir\requirements.txt"
& "$Prefix\venv\Scripts\pip.exe" install -e $RepoDir

nssm install AtulyaLaunch "$Prefix\venv\Scripts\python.exe" "-m uvicorn atulya_launch.web.app:create_app --factory --host 127.0.0.1 --port $Port"
nssm set AtulyaLaunch AppDirectory $RepoDir
nssm set AtulyaLaunch Start SERVICE_AUTO_START
nssm set AtulyaLaunch AppStdout "$Prefix\panel.log"
nssm set AtulyaLaunch AppStderr "$Prefix\panel.err"
Start-Service AtulyaLaunch
Write-Host "Atulya Launch is running at http://127.0.0.1:$Port"
