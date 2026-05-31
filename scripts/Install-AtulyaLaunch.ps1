param(
    [string]$Prefix = "",
    [string]$DataHome = "",
    [string]$Admin = "admin",
    [string]$Password = "",
    [switch]$All,
    [switch]$Local,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    $pythonArgs = @()
    $pythonExe = "python"
} else {
    $python = Get-Command py -ErrorAction SilentlyContinue
    if (-not $python) {
        throw "Python 3.9+ is required. Install Python from https://python.org and rerun this script."
    }
    $pythonArgs = @("-3")
    $pythonExe = "py"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installer = Join-Path $scriptDir "install.py"

$argsList = @()
if ($Prefix) { $argsList += @("--prefix", $Prefix) }
if ($DataHome) { $argsList += @("--home", $DataHome) }
if ($Admin) { $argsList += @("--admin", $Admin) }
if ($Password) { $argsList += @("--password", $Password) }
if ($All) { $argsList += "--all" }
if ($Local) { $argsList += "--local" }
if ($DryRun) { $argsList += "--dry-run" }

& $pythonExe @pythonArgs $installer @argsList
