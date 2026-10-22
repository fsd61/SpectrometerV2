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
      - CHANGELOG.md has a "## [<Version>]" section (used as the release notes)

    Then it creates an annotated tag v<Version>, pushes the tag to origin,
    pushes main plus the tag to github, and creates a GitHub Release with
    those notes and a SpectrometerV2-<Version>.zip source download attached
    (GitHub counts downloads of attached files, not of its automatic
    "Source code" links).

.EXAMPLE
    .\scripts\release.ps1 -Version 2.0.2

.EXAMPLE
    .\scripts\release.ps1 -Version 2.0.2 -ReleaseOnly    # retry just the GitHub Release
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version,

    # Only create the GitHub Release (notes + zip) for a tag that is already
    # published, e.g. to retry after a network failure. Skips tests and pushes.
    [switch]$ReleaseOnly
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$tag = "v$Version"

function Fail([string]$msg) { Write-Host "RELEASE ABORTED: $msg" -ForegroundColor Red; exit 1 }
function Invoke-Git { & git.exe @args; if ($LASTEXITCODE -ne 0) { Fail "git $($args -join ' ') failed" } }
. (Join-Path $PSScriptRoot 'github_api.ps1')

function Get-ReleaseNotes([string]$ver) {
    # The CHANGELOG section for this version: from "## [x.y.z]" to the next "## ".
    $lines = Get-Content (Join-Path $root 'CHANGELOG.md') -Encoding UTF8
    $start = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^## \[$([regex]::Escape($ver))\]") { $start = $i + 1; break }
    }
    if ($start -lt 0) { return $null }
    $end = $lines.Count
    for ($j = $start; $j -lt $lines.Count; $j++) { if ($lines[$j] -match '^## ') { $end = $j; break } }
    return (($lines[$start..($end - 1)]) -join "`n").Trim()
}

function Publish-GitHubRelease {
    $url = (git remote get-url github).Trim()
    if ($url -notmatch 'github\.com[/:]([^/]+)/([^/]+?)(\.git)?$') { Fail "cannot parse github remote URL: $url" }
    $repo = "$($Matches[1])/$($Matches[2])"

    $body = $script:notes + "`n`n---`nDownload **SpectrometerV2-$Version.zip** below, then follow the " +
        "[quick start](https://github.com/$repo#try-it-in-two-minutes-no-hardware-needed)."

    $zip = Join-Path $env:TEMP "SpectrometerV2-$Version.zip"
    Remove-Item $zip -ErrorAction SilentlyContinue
    Invoke-Git archive --format=zip --prefix="SpectrometerV2-$Version/" -o $zip $tag

    Write-Host "Creating GitHub release $tag..."
    try {
        $rel = Invoke-GitHubApi -Method Post -Path "repos/$repo/releases" -Body @{
            tag_name = $tag; name = "SpectrometerV2 $Version"; body = $body; make_latest = 'true'
        }
        $asset = Send-GitHubReleaseAsset -Release $rel -FilePath $zip
    } catch {
        Fail "GitHub release failed: $($_.Exception.Message). Retry with: .\scripts\release.ps1 -Version $Version -ReleaseOnly"
    } finally {
        Remove-Item $zip -ErrorAction SilentlyContinue
    }
    Write-Host "Release page: $($rel.html_url)"
    Write-Host "Download:     $($asset.browser_download_url)"
}

# --- Preconditions -----------------------------------------------------------
if ((git remote) -notcontains 'github') { Fail "no 'github' remote configured" }

$script:notes = Get-ReleaseNotes $Version
if (-not $script:notes) { Fail "CHANGELOG.md has no '## [$Version]' section to use as release notes" }

if ($ReleaseOnly) {
    git ls-remote --exit-code --tags github "refs/tags/$tag" *> $null
    if ($LASTEXITCODE -ne 0) { Fail "tag $tag is not on GitHub yet; run without -ReleaseOnly" }
    Publish-GitHubRelease
    exit 0
}

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
Publish-GitHubRelease

Write-Host "Released $tag to GitHub." -ForegroundColor Green
