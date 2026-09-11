$script:YanamiSubExpectedPublisher = "tuzibuqiahuluobo"
$script:YanamiSubCodeSigningOid = "1.3.6.1.5.5.7.3.3"

function Get-YanamiSubCodeSigningCertificate {
    param([switch]$Required)

    $PfxPath = $env:YANAMI_SUB_AUTHENTICODE_PFX
    $Thumbprint = $env:YANAMI_SUB_AUTHENTICODE_THUMBPRINT
    if ($PfxPath -and $Thumbprint) {
        throw "Set only one of YANAMI_SUB_AUTHENTICODE_PFX or YANAMI_SUB_AUTHENTICODE_THUMBPRINT."
    }
    if (-not $PfxPath -and -not $Thumbprint) {
        if ($Required) {
            throw @"
Authenticode signing is required, but no certificate is configured.
Set YANAMI_SUB_AUTHENTICODE_PFX and YANAMI_SUB_AUTHENTICODE_PASSWORD, or set
YANAMI_SUB_AUTHENTICODE_THUMBPRINT to a certificate in Cert:\CurrentUser\My.
"@
        }
        return $null
    }

    if ($PfxPath) {
        $ResolvedPfx = [System.IO.Path]::GetFullPath($PfxPath)
        if (-not (Test-Path -LiteralPath $ResolvedPfx -PathType Leaf)) {
            throw "Authenticode PFX not found: $ResolvedPfx"
        }
        $Certificate = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2
        $Flags = [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::UserKeySet `
            -bor [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::EphemeralKeySet
        $Certificate.Import(
            $ResolvedPfx,
            $env:YANAMI_SUB_AUTHENTICODE_PASSWORD,
            $Flags
        )
    }
    else {
        $Normalized = $Thumbprint.Replace(" ", "").ToUpperInvariant()
        $Certificate = Get-ChildItem -LiteralPath Cert:\CurrentUser\My |
            Where-Object { $_.Thumbprint -eq $Normalized } |
            Select-Object -First 1
        if (-not $Certificate) {
            throw "Authenticode certificate was not found in Cert:\CurrentUser\My: $Normalized"
        }
    }

    Assert-YanamiSubCodeSigningCertificate -Certificate $Certificate
    return $Certificate
}

function Assert-YanamiSubCodeSigningCertificate {
    param(
        [Parameter(Mandatory = $true)]
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate
    )

    $Publisher = $Certificate.GetNameInfo(
        [System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName,
        $false
    )
    if ($Publisher -cne $script:YanamiSubExpectedPublisher) {
        throw "Authenticode certificate publisher must be '$script:YanamiSubExpectedPublisher'; got '$Publisher'."
    }
    if (-not $Certificate.HasPrivateKey) {
        throw "Authenticode certificate has no private key."
    }
    $Now = Get-Date
    if ($Now -lt $Certificate.NotBefore -or $Now -gt $Certificate.NotAfter) {
        throw "Authenticode certificate is outside its validity period."
    }

    $Eku = $Certificate.Extensions |
        Where-Object { $_.Oid.Value -eq "2.5.29.37" } |
        Select-Object -First 1
    if (-not $Eku) {
        throw "Authenticode certificate has no Enhanced Key Usage extension."
    }
    $ParsedEku = New-Object `
        System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension(
            $Eku,
            $Eku.Critical
        )
    $HasCodeSigning = $ParsedEku.EnhancedKeyUsages |
        Where-Object { $_.Value -eq $script:YanamiSubCodeSigningOid }
    if (-not $HasCodeSigning) {
        throw "Authenticode certificate is not valid for Code Signing."
    }

    $Chain = New-Object System.Security.Cryptography.X509Certificates.X509Chain
    if (-not $Chain.Build($Certificate)) {
        $Reasons = ($Chain.ChainStatus | ForEach-Object { $_.Status }) -join ", "
        throw "Authenticode certificate is not trusted on this build machine: $Reasons"
    }
}

function Set-YanamiSubAuthenticodeSignature {
    param(
        [Parameter(Mandatory = $true)][string[]]$FilePath,
        [Parameter(Mandatory = $true)]
        [System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate
    )

    $TimestampServer = $env:YANAMI_SUB_AUTHENTICODE_TIMESTAMP_URL
    if (-not $TimestampServer) {
        $TimestampServer = "http://timestamp.digicert.com"
    }
    foreach ($RequestedPath in $FilePath) {
        $ResolvedPath = [System.IO.Path]::GetFullPath($RequestedPath)
        if (-not (Test-Path -LiteralPath $ResolvedPath -PathType Leaf)) {
            throw "Authenticode input not found: $ResolvedPath"
        }
        $Result = Set-AuthenticodeSignature `
            -LiteralPath $ResolvedPath `
            -Certificate $Certificate `
            -HashAlgorithm SHA256 `
            -TimestampServer $TimestampServer
        if ($Result.Status -ne "Valid") {
            throw "Authenticode signing failed for $ResolvedPath`: $($Result.Status) $($Result.StatusMessage)"
        }
        $Verified = Get-AuthenticodeSignature -LiteralPath $ResolvedPath
        $Publisher = $Verified.SignerCertificate.GetNameInfo(
            [System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName,
            $false
        )
        if ($Verified.Status -ne "Valid" -or $Publisher -cne $script:YanamiSubExpectedPublisher) {
            throw "Authenticode verification failed for $ResolvedPath."
        }
    }
}

function Get-YanamiSubPackagedExecutables {
    param([Parameter(Mandatory = $true)][string]$ApplicationDirectory)

    $Candidates = @(
        (Join-Path $ApplicationDirectory "Yanami Sub.exe"),
        (Join-Path $ApplicationDirectory "updater\Yanami Sub Updater.exe")
    )
    foreach ($Candidate in $Candidates) {
        if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) {
            throw "Packaged executable required for Authenticode signing was not found: $Candidate"
        }
    }
    return $Candidates
}
