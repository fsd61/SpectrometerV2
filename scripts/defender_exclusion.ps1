<#
.SYNOPSIS
    Add, remove, or list a Microsoft Defender folder exclusion for this
    project's virtual environment.

.DESCRIPTION
    Defender's real-time scanner inspects every DLL and .pyd loaded at process
    start. SpectrometerV2's GUI loads PySide6 (large Qt DLLs) and pyqtgraph
    (several hundred small modules), so a cold start pays a substantial scanning
    cost that does not show up in `python -X importtime` output.

    Excluding the .venv directory removes that cost. It also means Defender will
    NOT scan anything inside .venv -- including packages you install later. Only
    do this on a development machine, keep the exclusion scoped to .venv (not the
    whole project, which holds the source you edit), and remove it with -Remove
    if you stop needing it.

.PARAMETER Path
    Folder to exclude. Defaults to <repo>\.venv.

.PARAMETER Remove
    Remove the exclusion instead of adding it.

.PARAMETER List
    Show the current Defender path exclusions and exit.

.EXAMPLE
    # From an elevated PowerShell prompt, in the repo root:
    .\scripts\defender_exclusion.ps1

.EXAMPLE
    .\scripts\defender_exclusion.ps1 -Remove

.NOTES
    Requires an elevated (Administrator) PowerShell session. Tamper Protection
    or a group policy may block exclusion changes; the script reports that
    rather than failing silently.
#>
[CmdletBinding()]
param(
    [string]$Path,
    [switch]$Remove,
    [switch]$List
)

$ErrorActionPreference = 'Stop'

function Test-Elevated {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Get-Command Add-MpPreference -ErrorAction SilentlyContinue)) {
    Write-Error "Microsoft Defender cmdlets are unavailable on this machine (Defender may be disabled or replaced by another antivirus). Nothing to do."
    exit 1
}

if ($List) {
    Write-Host "Current Defender path exclusions:" -ForegroundColor Cyan
    $current = (Get-MpPreference).ExclusionPath
    if ($current) { $current | ForEach-Object { Write-Host "  $_" } }
    else { Write-Host "  (none)" }
    exit 0
}

if (-not (Test-Elevated)) {
    Write-Error "This script must run in an elevated PowerShell session. Right-click PowerShell -> 'Run as Administrator', then re-run it."
    exit 1
}

$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $Path) { $Path = Join-Path $repoRoot '.venv' }

if (-not (Test-Path -LiteralPath $Path)) {
    Write-Error "Path not found: $Path"
    exit 1
}
$Path = (Resolve-Path -LiteralPath $Path).Path

$existing = @((Get-MpPreference).ExclusionPath)

try {
    if ($Remove) {
        if ($existing -notcontains $Path) {
            Write-Host "Not currently excluded: $Path" -ForegroundColor Yellow
            exit 0
        }
        Remove-MpPreference -ExclusionPath $Path
        Write-Host "Removed Defender exclusion: $Path" -ForegroundColor Green
    }
    else {
        if ($existing -contains $Path) {
            Write-Host "Already excluded: $Path" -ForegroundColor Yellow
            exit 0
        }
        Add-MpPreference -ExclusionPath $Path
        Write-Host "Added Defender exclusion: $Path" -ForegroundColor Green
        Write-Host "Defender will no longer scan files in this folder. Undo with: .\scripts\defender_exclusion.ps1 -Remove" -ForegroundColor DarkGray
    }
}
catch {
    Write-Error "Could not change Defender exclusions: $($_.Exception.Message)`nThis is usually Tamper Protection (Windows Security -> Virus & threat protection -> Manage settings) or a group policy."
    exit 1
}

Write-Host ""
Write-Host "To measure the effect, time a cold start before and after:" -ForegroundColor Cyan
Write-Host '  Measure-Command { .\.venv\Scripts\python.exe -c "import ui.qt.main_window" }' -ForegroundColor DarkGray
Write-Host "  (run it twice; the first is cold, the second warm)" -ForegroundColor DarkGray
