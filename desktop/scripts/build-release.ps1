[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [ValidateSet("stable", "beta")][string]$Channel = "stable",
    [Parameter(Mandatory = $true)][string]$KeyId,
    [Parameter(Mandatory = $true)][string]$PrivateKeyPath,
    [string]$VenvPath = "",
    [string]$BootstrapDirectory = "",
    [string]$UpstreamDirectory = "",
    # This is the first release in the independent desktop version line, so no
    # older build may take an app-only delta. An empty SupportedFrom list makes
    # every earlier installation use the complete package, which is the safe
    # default until a later desktop release explicitly opts in compatible builds.
    [string]$MinimumLauncherVersion = "0.1.0-rc.1",
    [string]$MinimumSupportedVersion = "0.1.0-rc.1",
    [string[]]$SupportedFrom = @(),
    [string]$ReleaseNotes = "",
    [string]$Repository = "tuzibuqiahuluobo/finesub-desktop",
    [switch]$SkipBootstrap,
    [switch]$RequireAuthenticode
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $PSScriptRoot "authenticode.ps1")
$SigningCertificate = Get-FineSubCodeSigningCertificate `
    -Required:$RequireAuthenticode
if (-not $VenvPath) {
    if ($env:FINESUB_DESKTOP_VENV) {
        $VenvPath = $env:FINESUB_DESKTOP_VENV
    }
    else {
        $VenvPath = Join-Path $RepoRoot ".venv-desktop"
    }
}
$Python = Join-Path ([System.IO.Path]::GetFullPath($VenvPath)) "Scripts\python.exe"
if (-not $BootstrapDirectory) {
    $BootstrapDirectory = Join-Path $RepoRoot "dist\bootstrap"
    if ($BootstrapDirectory -match "[^\u0000-\u007F]") {
        $BootstrapDirectory = Join-Path `
            ([System.IO.Path]::GetTempPath()) `
            "finesub-build\$Version"
    }
}
$BootstrapDirectory = [System.IO.Path]::GetFullPath($BootstrapDirectory)
$Bootstrap = Join-Path $BootstrapDirectory "FineSub Desktop.dist"
if (-not $SkipBootstrap) {
    & (Join-Path $PSScriptRoot "build-bootstrap.ps1") `
        -VenvPath $VenvPath `
        -OutputDirectory $BootstrapDirectory `
        -UpstreamDirectory $UpstreamDirectory `
        -Version $Version
}
if ($SigningCertificate) {
    Set-FineSubAuthenticodeSignature `
        -FilePath (Get-FineSubPackagedExecutables $Bootstrap) `
        -Certificate $SigningCertificate
}
$AppSource = Join-Path $Bootstrap "app\versions\$Version"
if (-not (Test-Path -LiteralPath $AppSource -PathType Container)) {
    throw "App source does not exist: $AppSource"
}
$Arguments = @(
    "-m", "desktop.scripts.build_release",
    "--version", $Version,
    "--channel", $Channel,
    "--key-id", $KeyId,
    "--private-key", ([System.IO.Path]::GetFullPath($PrivateKeyPath)),
    "--app-source", $AppSource,
    "--full-source", $Bootstrap,
    "--output-dir", (Join-Path $RepoRoot "dist\release"),
    "--minimum-launcher", $MinimumLauncherVersion,
    "--minimum-supported", $MinimumSupportedVersion,
    "--repository", $Repository
)
# Appended only when it has a value. Windows PowerShell 5.1 silently DROPS an
# empty string when splatting an array to a native command, so passing
# `--release-notes ""` there leaves argparse looking at the next flag and
# failing with "expected one argument". pwsh 7 keeps the empty argument, which
# is why this never showed up locally -- it took a CI run, whose shell is 5.1,
# to surface it. argparse defaults this to "" anyway, so omitting it is exact.
if ($ReleaseNotes) {
    $Arguments += @("--release-notes", $ReleaseNotes)
}
foreach ($VersionValue in $SupportedFrom) {
    $Arguments += @("--supported-from", $VersionValue)
}
Push-Location $RepoRoot
try {
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Release asset generation failed."
    }
}
finally {
    Pop-Location
}
