# Shared source validation and tracked-file staging for local and cloud builds.
function Get-CleanSourceCommit {
    param([Parameter(Mandatory = $true)][string]$Path)

    $Changes = @(& git -C $Path status --porcelain --untracked-files=no)
    if ($LASTEXITCODE -ne 0 -or $Changes.Count -gt 0) {
        throw "Release source has uncommitted tracked changes: $Path"
    }
    $Commit = (& git -C $Path rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $Commit -notmatch '^[0-9a-f]{40}$') {
        throw "Cannot determine release source commit: $Path"
    }
    return $Commit
}

function Get-VerifiedCoreSource {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [string]$CoreRoot = ""
    )

    $Pin = Get-Content -LiteralPath (Join-Path $RepoRoot "desktop\resources\core-source.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Pin.commit -notmatch '^[0-9a-f]{40}$' -or $Pin.tag -ne "v$($Pin.version)") {
        throw "Invalid pinned FineSub source descriptor."
    }
    $Project = Get-Content -LiteralPath (Join-Path $RepoRoot "pyproject.toml") -Raw -Encoding UTF8
    if ($Project -notmatch '"finesub==(?<version>[^"; ]+)"' -or $Matches.version -ne $Pin.version) {
        throw "Desktop dependency does not match core-source.json."
    }
    if (-not $CoreRoot) { $CoreRoot = $env:FINESUB_UPSTREAM_SOURCE }
    if (-not $CoreRoot) { throw "Pass -UpstreamDirectory or set FINESUB_UPSTREAM_SOURCE to the pinned FineSub checkout." }
    $CoreRoot = (Resolve-Path -LiteralPath $CoreRoot).Path
    $Commit = Get-CleanSourceCommit -Path $CoreRoot
    $Version = (Get-Content -LiteralPath (Join-Path $CoreRoot "VERSION") -Raw -Encoding UTF8).Trim()
    if ($Commit -ne $Pin.commit -or $Version -ne $Pin.version) {
        throw "FineSub source must be $($Pin.tag) at $($Pin.commit); got $Version at $Commit."
    }
    $Required = @(
        "src/finesub/pipeline.py",
        "src/finesub_bootstrap/environment.py",
        "src/finesub_bootstrap/runtime-manifest.json",
        "src/finesub_bootstrap/model-manifest.json",
        "src/finesub_bootstrap/download-sources.json",
        "src/finesub_bootstrap/pylock.win-py312.toml",
        "src/finesub_bootstrap/pylock.win-py312.cn.toml"
    )
    foreach ($Relative in $Required) {
        if (-not (Test-Path -LiteralPath (Join-Path $CoreRoot $Relative) -PathType Leaf)) {
            throw "Pinned core input is missing: $Relative"
        }
    }
    $Tracked = @(& git -C $CoreRoot ls-files --error-unmatch -- $Required)
    if ($LASTEXITCODE -ne 0 -or $Tracked.Count -ne $Required.Count) {
        throw "Core runtime inputs must be tracked by the pinned checkout."
    }
    return [pscustomobject]@{ Root = $CoreRoot; Version = $Version; Commit = $Commit }
}

function Assert-PythonCoreSource {
    param(
        [Parameter(Mandatory = $true)][string]$Python,
        [Parameter(Mandatory = $true)]$CoreSource
    )

    $Check = @'
from importlib.metadata import version
from importlib.util import find_spec
from pathlib import Path
import sys
root = (Path(sys.argv[1]) / "src").resolve()
if version("finesub") != sys.argv[2]:
    raise SystemExit("Build interpreter has the wrong FineSub version")
for name in ("finesub", "finesub_bootstrap"):
    spec = find_spec(name)
    if spec is None or spec.origin is None or Path(spec.origin).resolve().parent != root / name:
        raise SystemExit(f"Build interpreter loads {name} outside the pinned source")
'@
    $Check | & $Python - $CoreSource.Root $CoreSource.Version
    if ($LASTEXITCODE -ne 0) {
        throw "Build Python must use the verified editable FineSub checkout. Run setup-dev.ps1 -UpstreamDirectory with that checkout."
    }
}

function Copy-TrackedTree {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$RelativeRoot,
        [Parameter(Mandatory = $true)][string]$Destination,
        [switch]$PythonOnly
    )

    $Tracked = @(& git -C $RepoRoot ls-files --cached --full-name -- $RelativeRoot)
    if ($LASTEXITCODE -ne 0) { throw "git ls-files failed for $RelativeRoot; refusing to guess what to ship" }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $Prefix = $RelativeRoot.Replace('\', '/').TrimEnd('/') + '/'
    foreach ($Relative in $Tracked) {
        $Normalized = $Relative.Replace('\', '/')
        if (-not $Normalized.StartsWith($Prefix)) { continue }
        $Tail = $Normalized.Substring($Prefix.Length)
        if ($Tail -match '(^|/)(tests|__pycache__)(/|$)' -or $Tail -match '[.](pyc|pyo)$') { continue }
        if ($PythonOnly -and -not $Tail.EndsWith('.py')) { continue }
        $Source = Join-Path $RepoRoot ($Normalized.Replace('/', '\'))
        if ((Get-Item -LiteralPath $Source -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            throw "Release source cannot contain a reparse point: $Normalized"
        }
        $Target = Join-Path $Destination ($Tail.Replace('/', '\'))
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Target) | Out-Null
        Copy-Item -LiteralPath $Source -Destination $Target -Force
    }
}

function Assert-PackagedCoreSource {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$VersionRoot
    )

    $Pin = Get-Content -LiteralPath (Join-Path $RepoRoot "desktop\resources\core-source.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    $Manifest = Get-Content -LiteralPath (Join-Path $VersionRoot "app-manifest.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Manifest.coreVersion -ne $Pin.version -or $Manifest.coreCommit -ne $Pin.commit) {
        throw "Packaged core provenance does not match the approved source; rebuild the bootstrap."
    }
    if ((Get-Content -LiteralPath (Join-Path $VersionRoot "VERSION") -Raw -Encoding UTF8).Trim() -ne $Manifest.version) {
        throw "Packaged VERSION does not match its app manifest."
    }
    foreach ($Relative in @(
        "VERSION",
        "desktop/resources/core-source.json",
        "src/finesub_bootstrap/runtime-manifest.json",
        "src/finesub_bootstrap/model-manifest.json",
        "src/finesub_bootstrap/download-sources.json",
        "src/finesub_bootstrap/pylock.win-py312.toml",
        "src/finesub_bootstrap/pylock.win-py312.cn.toml"
    )) {
        $File = Join-Path $VersionRoot $Relative
        $Expected = $Manifest.files.$Relative.sha256
        if (-not $Expected) {
            throw "Packaged core input differs from its build receipt: $Relative"
        }
        # Legacy PowerShell children may not discover utility modules.
        $Hasher = [System.Security.Cryptography.SHA256]::Create()
        try {
            $Actual = [System.BitConverter]::ToString(
                $Hasher.ComputeHash([System.IO.File]::ReadAllBytes($File))
            ).Replace('-', '').ToLowerInvariant()
        }
        finally {
            $Hasher.Dispose()
        }
        if ($Actual -ne $Expected) {
            throw "Packaged core input differs from its build receipt: $Relative"
        }
    }
}
