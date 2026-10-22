<#
.SYNOPSIS
    Minimal GitHub REST helpers, authenticated with the GitHub sign-in that Git
    Credential Manager already stores for git pushes. Dot-source this file.
    No token is ever written to disk or printed.
#>

function Get-GitHubToken {
    $req = "protocol=https`nhost=github.com`n`n"
    $out = $req | & git.exe credential fill 2>$null
    $line = $out | Where-Object { $_ -like 'password=*' } | Select-Object -First 1
    if (-not $line) { throw "No GitHub credential found. Run any 'git push github' once to sign in." }
    return $line.Substring(9)
}

function Invoke-GitHubApi {
    param(
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$Path,
        $Body = $null
    )
    $headers = @{
        Authorization          = "Bearer $(Get-GitHubToken)"
        Accept                 = 'application/vnd.github+json'
        'X-GitHub-Api-Version' = '2022-11-28'
        'User-Agent'           = 'SpectrometerV2-release'
    }
    $uri = if ($Path -match '^https://') { $Path } else { "https://api.github.com/$($Path.TrimStart('/'))" }
    $params = @{ Method = $Method; Uri = $uri; Headers = $headers; UseBasicParsing = $true }
    if ($null -ne $Body) {
        $params.Body = [Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 10))
        $params.ContentType = 'application/json; charset=utf-8'
    }
    Invoke-RestMethod @params
}

function Send-GitHubReleaseAsset {
    param(
        [Parameter(Mandatory = $true)]$Release,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string]$ContentType = 'application/zip'
    )
    $name = [Uri]::EscapeDataString((Split-Path -Leaf $FilePath))
    $uploadUri = ($Release.upload_url -replace '\{.*\}$', '') + "?name=$name"
    $headers = @{
        Authorization          = "Bearer $(Get-GitHubToken)"
        Accept                 = 'application/vnd.github+json'
        'X-GitHub-Api-Version' = '2022-11-28'
        'User-Agent'           = 'SpectrometerV2-release'
    }
    Invoke-RestMethod -Method Post -Uri $uploadUri -Headers $headers -ContentType $ContentType `
        -InFile $FilePath -UseBasicParsing
}
