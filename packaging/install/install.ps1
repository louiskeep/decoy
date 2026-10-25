# Decoy CLI installer (Windows, PowerShell).
#
# Windows analogue of install.sh: it verifies a checksum and a signature BEFORE
# it extracts anything, and a bad checksum or signature is a hard stop with
# nothing installed. It lays down a managed runtime under %USERPROFILE%\.decoy
# and a decoy.cmd shim on PATH.
#
# NOTE: this environment has no Windows runner, so this script is verified by
# inspection and mirrors the proven install.sh verify-before-extract flow; its
# real verification runs in CI / on a Windows host as part of the per-target
# smoke (packaging/README.md). It uses the same ECDSA-P256/SHA-256 signature
# over the SHA256SUMS manifest, verified with the bundled openssl (shipped in
# the embedded runtime is not available pre-install, so a system openssl or the
# one on PATH is used; Windows git ships one).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File install.ps1 [-Version X.Y.Z]
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall
#
# Config (env; defaults are the real self-hosted channel):
#   DECOY_INSTALL_HOME, DECOY_INSTALL_BIN, DECOY_INSTALL_BASE_URL,
#   DECOY_INSTALL_LOCAL_DIR, DECOY_INSTALL_PUBKEY  (same meanings as install.sh)
[CmdletBinding()]
param(
    [string]$Version = "",
    [switch]$Uninstall
)
$ErrorActionPreference = "Stop"

function Die($msg) { Write-Error "decoy-install: $msg"; exit 1 }
function Info($msg) { Write-Host "decoy-install: $msg" }

$InstallHome = if ($env:DECOY_INSTALL_HOME) { $env:DECOY_INSTALL_HOME } else { Join-Path $env:USERPROFILE ".decoy" }
$InstallBin  = if ($env:DECOY_INSTALL_BIN) { $env:DECOY_INSTALL_BIN } else { Join-Path $env:USERPROFILE ".local\bin" }
$BaseUrl     = if ($env:DECOY_INSTALL_BASE_URL) { $env:DECOY_INSTALL_BASE_URL } else { "https://decoy.dev/cli" }
$LocalDir    = $env:DECOY_INSTALL_LOCAL_DIR
$PubKeyOvr   = $env:DECOY_INSTALL_PUBKEY

# THIS IS A LOCAL TEST KEY (packaging/sign/README.md); the real release build
# swaps this block for the real public key.
$EmbeddedPubKey = @"
-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEE474c7kSNltShBhZahXv3Ny74pdQ
kgpAWRkfzJb6n4cuudOalN2Upm2mVDBfVq6pkmSeFc69GcbotqFde4ruhQ==
-----END PUBLIC KEY-----
"@

function Detect-Target {
    $arch = $env:PROCESSOR_ARCHITECTURE
    switch ($arch) {
        "AMD64" { return "windows-x86_64" }
        "x86"   { return "windows-x86_64" }
        default { Die "unsupported Windows architecture '$arch'. Supported: windows-x86_64. No install performed." }
    }
}

function Fetch($rel, $dest) {
    if ($LocalDir) {
        $src = Join-Path $LocalDir $rel
        if (-not (Test-Path $src)) { Die "artifact not found in local dir: $rel" }
        Copy-Item $src $dest -Force
    } else {
        try { Invoke-WebRequest -Uri "$BaseUrl/$rel" -OutFile $dest -UseBasicParsing }
        catch { Die "download failed: $BaseUrl/$rel" }
    }
}

if ($Uninstall) {
    $launcher = Join-Path $InstallBin "decoy.cmd"
    if (Test-Path $launcher) { Remove-Item $launcher -Force; Info "removed launcher $launcher" }
    if (Test-Path $InstallHome) { Remove-Item $InstallHome -Recurse -Force; Info "removed managed runtime $InstallHome" }
    Info "uninstalled."
    exit 0
}

$openssl = (Get-Command openssl -ErrorAction SilentlyContinue)
if (-not $openssl) { Die "openssl is required to verify the signature (Windows git ships one)" }

$target = Detect-Target
Info "target: $target"

$staging = Join-Path ([System.IO.Path]::GetTempPath()) ("decoy-install." + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $staging | Out-Null
try {
    if (-not $Version) {
        Fetch "version.json" (Join-Path $staging "version.json")
        $doc = Get-Content (Join-Path $staging "version.json") -Raw | ConvertFrom-Json
        $Version = $doc.latest
        if (-not $Version) { Die "could not read 'latest' from version.json" }
    }
    Info "version: $Version"

    $tarball = "decoy-$Version-$target.tar.gz"
    Fetch "$Version/$tarball" (Join-Path $staging $tarball)
    Fetch "$Version/SHA256SUMS" (Join-Path $staging "SHA256SUMS")
    Fetch "$Version/SHA256SUMS.sig" (Join-Path $staging "SHA256SUMS.sig")

    $pubkey = Join-Path $staging "decoy-release.pub"
    if ($PubKeyOvr) {
        if (-not (Test-Path $PubKeyOvr)) { Die "pubkey not found: $PubKeyOvr" }
        Copy-Item $PubKeyOvr $pubkey -Force
    } else {
        Set-Content -Path $pubkey -Value $EmbeddedPubKey -NoNewline
    }

    # 1. Verify the manifest signature.
    & openssl dgst -sha256 -verify $pubkey -signature (Join-Path $staging "SHA256SUMS.sig") (Join-Path $staging "SHA256SUMS") | Out-Null
    if ($LASTEXITCODE -ne 0) { Die "SIGNATURE VERIFICATION FAILED for SHA256SUMS. Refusing to install." }
    Info "signature OK"

    # 2. Verify the tarball against the trusted manifest.
    $expected = (Select-String -Path (Join-Path $staging "SHA256SUMS") -Pattern ([regex]::Escape($tarball)) | Select-Object -First 1).Line.Split(" ")[0]
    if (-not $expected) { Die "no checksum for $tarball in SHA256SUMS. Refusing to install." }
    $actual = (Get-FileHash -Algorithm SHA256 (Join-Path $staging $tarball)).Hash.ToLower()
    if ($expected -ne $actual) { Die "CHECKSUM MISMATCH for $tarball. Refusing to install." }
    Info "checksum OK"

    # Verified. Extract, flip current, place the launcher.
    $versionDir = Join-Path (Join-Path $InstallHome "versions") $Version
    if (Test-Path $versionDir) { Remove-Item $versionDir -Recurse -Force }
    New-Item -ItemType Directory -Path $versionDir | Out-Null
    & tar -xzf (Join-Path $staging $tarball) -C $versionDir
    if ($LASTEXITCODE -ne 0) { Die "extraction failed" }
    if (-not (Test-Path (Join-Path $versionDir "bundle-manifest.json"))) {
        $inner = Get-ChildItem $versionDir -Directory | Select-Object -First 1
        if ($inner -and (Test-Path (Join-Path $inner.FullName "bundle-manifest.json"))) {
            Get-ChildItem $inner.FullName -Force | Move-Item -Destination $versionDir
            Remove-Item $inner.FullName -Force
        }
    }
    if (-not (Test-Path (Join-Path $versionDir "bundle-manifest.json"))) { Die "bundle is malformed: no bundle-manifest.json after extract" }

    $current = Join-Path $InstallHome "current"
    if (Test-Path $current) { Remove-Item $current -Force -Recurse }
    New-Item -ItemType Junction -Path $current -Target $versionDir | Out-Null

    New-Item -ItemType Directory -Path $InstallBin -Force | Out-Null
    $shimTarget = Join-Path (Join-Path $current "bin") "decoy.cmd"
    Set-Content -Path (Join-Path $InstallBin "decoy.cmd") -Value "@echo off`r`n`"$shimTarget`" %*`r`n"

    Info "installed decoy $Version for $target."
    Info "launcher: $(Join-Path $InstallBin 'decoy.cmd')"
} finally {
    Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
}
