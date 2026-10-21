<#
.SYNOPSIS
    Publish a verified release of main to GitHub.

.DESCRIPTION
    The home server (remote "origin") holds all work in progress. GitHub
    (remote "github") only ever receives main and release tags, and only
    through this script, so it can lag origin but never diverge from it.

    Refuses to publish unless:
      - the current branch is main
      - there are no uncommitted changes to tracked files
      - pyproject.toml's version equals -Version
      - tag v<Version> does not already exist
      - local main is already pushed to origin (home is never behind GitHub)
      - the full test suite passes

    Then it creates an annotated tag v<Version>, pushes the tag to origin,
    and pushes main plus the tag to github.

.EXAMPLE
    .\scripts\release.ps1 -Version 2.0.0
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$tag = "v$Version"

function Fail([string]$msg) { Write-Host "RELEASE ABORTED: $msg" -ForegroundColor Red; exit 1 }
function Invoke-Git { & git.exe @args; if ($LASTEXITCODE -ne 0) { Fail "git $($args -join ' ') failed" } }

# --- Preconditions -----------------------------------------------------------
if ((git remote) -notcontains 'github') { Fail "no 'github' remote configured" }

$branch = (git branch --show-current).Trim()
if ($branch -ne 'main') { Fail "on branch '$branch'; releases are cut from main" }

if (git status --porcelain --untracked-files=no) { Fail "uncommitted changes to tracked files" }

$pyVersion = (Select-String -Path pyproject.toml -Pattern '^\s*version\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
if ($pyVersion -ne $Version) { Fail "pyproject.toml version is '$pyVersion', not '$Version'" }
$appVersion = (Select-String -Path src\app\__init__.py -Pattern '^__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
if ($appVersion -ne $Version) { Fail "src/app/__init__.py __version__ is '$appVersion', not '$Version'" }

git rev-parse -q --verify "refs/tags/$tag" *> $null
if ($LASTEXITCODE -eq 0) { Fail "tag $tag already exists" }

Write-Host "Checking origin..."
Invoke-Git fetch origin main
if ((git rev-parse main) -ne (git rev-parse origin/main)) {
    Fail "local main differs from origin/main; push to the home server first"
}

# --- Verify -----------------------------------------------------------------
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { Fail "no virtualenv at .venv" }
Write-Host "Running test suite..."
& $python -m pytest -q -p no:cacheprovider
if ($LASTEXITCODE -ne 0) { Fail "tests failed" }

# --- Publish ----------------------------------------------------------------
Invoke-Git tag -a $tag -m "SpectrometerV2 $Version"
Invoke-Git push origin "refs/tags/${tag}"
Invoke-Git push github "refs/heads/main:refs/heads/main" "refs/tags/${tag}"

Write-Host "Released $tag to GitHub." -ForegroundColor Green
