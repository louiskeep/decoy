<#
.SYNOPSIS
  Decoy CLI installer for Windows (PowerShell): self-hosted, signed, per-platform bundle.

.DESCRIPTION
  The Windows parallel of install.sh. Lays down a managed, self-contained runtime
  (bundled CPython + matched engine/native/CLI wheels) under %USERPROFILE%\.decoy and a
  `decoy.cmd` launcher on PATH. Verifies the hosted version document's Ed25519 signature
  AND the bundle's Ed25519 signature AND a SHA-256 checksum BEFORE anything is laid down.
  A failed signature or checksum is a HARD REFUSAL.

  Checksum: Get-FileHash (built in). Signature: Ed25519 is NOT in the .NET Framework
  that ships with Windows PowerShell 5.1, so verification uses `openssl` on PATH (git for
  Windows / scoop / choco provide it). If openssl is absent the install REFUSES loudly
  rather than skipping signature verification. (The signing-tool choice for Windows is an
  open lane decision -- see packaging_tools/README.md; a bundled minisign is the
  alternative if requiring openssl proves to be friction.)

.PARAMETER Version
  Install this exact version instead of latest.

.PARAMETER Uninstall
  Remove the managed runtime and the launcher.
#>
[CmdletBinding()]
param(
  [string]$Version = "",
  [switch]$Uninstall
)
$ErrorActionPreference = "Stop"

$DecoyHome = if ($env:DECOY_HOME) { $env:DECOY_HOME } else { Join-Path $env:USERPROFILE ".decoy" }
$BinDir    = if ($env:DECOY_BIN_DIR) { $env:DECOY_BIN_DIR } else { Join-Path $env:USERPROFILE ".decoy\bin" }
$VersionUrl = if ($env:DECOY_VERSION_URL) { $env:DECOY_VERSION_URL } else { "https://decoy.dev/cli/version.json" }

# Pinned release public key. DEV/PLACEHOLDER -- filled with the real key at release
# publish, the same key install.sh pins. DECOY_RELEASE_PUBKEY_FILE overrides (testing).
$PinnedPubKey = @"
-----BEGIN PUBLIC KEY-----
__DECOY_RELEASE_PUBLIC_KEY__
-----END PUBLIC KEY-----
"@

function Die($msg) { Write-Error "decoy install: $msg"; exit 1 }
function Info($msg) { Write-Host "decoy install: $msg" }

function Resolve-Target {
  # Windows is GATED OFF the advertised matrix this cycle. The managed-runtime model is
  # POSIX-shaped (a `current` symlink swap + a python/bin/python3 launcher) and the
  # Windows install/upgrade/rollback lifecycle could not be verified end to end in this
  # remediation cycle (no Windows runner). Per the launch rule we refuse rather than
  # advertise an unrunnable path. See
  # docs/distribution/decisions/2026-10-26-windows-target-gated.md.
  # To re-enable: return "windows-x86_64" for AMD64 here, re-add it to
  # decoy.distribution.targets.SUPPORTED_TARGETS + the build, and verify the lifecycle
  # end to end (the install body below is kept corrected for that day).
  return ""
}

function Verify-Sig($dataFile, $sigB64File, $pubFile) {
  # Raw detached Ed25519 via openssl -- identical bytes to decoy.distribution.signing.
  $openssl = Get-Command openssl -ErrorAction SilentlyContinue
  if (-not $openssl) { Die "openssl not found on PATH; cannot verify the Ed25519 signature. Install Git for Windows or openssl, then retry. (Refusing rather than skipping verification.)" }
  $raw = New-TemporaryFile
  & openssl base64 -d -A -in $sigB64File -out $raw 2>$null
  & openssl pkeyutl -verify -pubin -inkey $pubFile -rawin -in $dataFile -sigfile $raw *> $null
  $ok = ($LASTEXITCODE -eq 0)
  Remove-Item $raw -Force -ErrorAction SilentlyContinue
  return $ok
}

if ($Uninstall) {
  Info "removing $DecoyHome and $BinDir\decoy.cmd"
  Remove-Item (Join-Path $BinDir "decoy.cmd") -Force -ErrorAction SilentlyContinue
  Remove-Item $DecoyHome -Recurse -Force -ErrorAction SilentlyContinue
  Info "uninstalled."
  exit 0
}

$target = Resolve-Target
if (-not $target) { Die "Windows is not a supported target at launch (gated off the advertised matrix this cycle; see docs/distribution/decisions/2026-10-26-windows-target-gated.md). No install performed." }
Info "target: $target"

# First-install-only bootstrap (Cam decision), mirroring install.sh. This script lays down
# a FRESH runtime and REFUSES to replace an existing one: it never moves aside, deletes, or
# overwrites a managed runtime, so it has no backup/restore recovery to get wrong. All
# same-version repair and every upgrade go through `decoy upgrade`, which stages a fresh
# version dir and flips `current` atomically. Refuse before any download or extraction.
$versions = Join-Path $DecoyHome "versions"
$hasVersionDir = (Test-Path $versions) -and @(Get-ChildItem $versions -Directory -ErrorAction SilentlyContinue | Where-Object { -not $_.Name.StartsWith(".") }).Count -gt 0
if ((Test-Path (Join-Path $DecoyHome "current")) -or $hasVersionDir) {
  Info "an existing Decoy runtime is installed at $DecoyHome."
  Info "this bootstrap installs only; it will NOT replace an existing runtime."
  Info "to upgrade or repair, run:  decoy upgrade        (repair: decoy upgrade --force)"
  Die "refusing to overwrite an existing install"
}

$work = New-Item -ItemType Directory -Path (Join-Path $env:TEMP ("decoy-install-" + [guid]::NewGuid()))
try {
  $pub = Join-Path $work "pub.pem"
  if ($env:DECOY_RELEASE_PUBKEY_FILE) { Copy-Item $env:DECOY_RELEASE_PUBKEY_FILE $pub }
  else { Set-Content -Path $pub -Value $PinnedPubKey -NoNewline }

  $baseUrl = $VersionUrl -replace '/[^/]*$',''

  $vdoc = Join-Path $work "version.json"
  Invoke-WebRequest -Uri $VersionUrl -OutFile $vdoc -UseBasicParsing
  Invoke-WebRequest -Uri "$VersionUrl.sig" -OutFile "$vdoc.sig" -UseBasicParsing
  if (-not (Verify-Sig $vdoc "$vdoc.sig" $pub)) { Die "version-document signature INVALID -- refusing (possible tampering)" }
  Info "version document signature verified"

  $doc = Get-Content $vdoc -Raw | ConvertFrom-Json
  $ver = if ($Version) { $Version } else { $doc.latest }
  if (-not $ver) { Die "version document has no 'latest'" }

  if ($ver -eq $doc.latest) {
    $art = $doc.artifacts.$target
    if (-not $art) { Die "version document lists no bundle for $target" }
    $url = $art.url; $expectSha = $art.sha256; $sigUrl = $art.sig
  } else {
    $url = "$baseUrl/$ver/decoy-$ver-$target.tar.gz"; $sigUrl = "$url.sig"; $expectSha = ""
  }

  $tarball = Join-Path $work "decoy-$ver-$target.tar.gz"
  Invoke-WebRequest -Uri $url -OutFile $tarball -UseBasicParsing
  Invoke-WebRequest -Uri $sigUrl -OutFile "$tarball.sig" -UseBasicParsing

  if ($expectSha) {
    $got = (Get-FileHash -Algorithm SHA256 $tarball).Hash.ToLower()
    if ($got -ne $expectSha.ToLower()) { Die "bundle checksum MISMATCH (expected $expectSha got $got) -- refusing" }
    Info "bundle checksum verified"
  }
  if (-not (Verify-Sig $tarball "$tarball.sig" $pub)) { Die "bundle signature INVALID -- refusing (possible tampering)" }
  Info "bundle signature verified"

  # $versions was set above, where the first-install-only guard already refused any
  # existing runtime.
  New-Item -ItemType Directory -Force -Path $versions | Out-Null
  $incoming = Join-Path $versions (".incoming." + [guid]::NewGuid())
  New-Item -ItemType Directory -Force -Path $incoming | Out-Null
  # tar ships with Windows 10+; extracts .tar.gz.
  & tar -xzf $tarball -C $incoming
  $bundleRoot = Get-ChildItem $incoming -Directory | Select-Object -First 1
  if (-not $bundleRoot) { Die "bundle archive is malformed (no top-level dir)" }
  $pybin = Join-Path $bundleRoot.FullName "python\python.exe"
  if (-not (Test-Path $pybin)) { $pybin = Join-Path $bundleRoot.FullName "python\bin\python.exe" }
  if (-not (Test-Path $pybin)) { Die "bundle is missing its interpreter" }

  # The bundled interpreter runs IMPORT-ISOLATED and bytecode-free (-I -B):
  #  -I drops the CWD and PYTHONPATH/PYTHON* env from sys.path, so this bootstrap cannot
  #     be tricked into importing a planted decoy/decoy_engine package from a hostile
  #     working dir and forging a passing verify/self-check.
  #  -B keeps bytecode writes off: the manifest signs no caches and the verifier rejects
  #     any found on disk, so these install-time checks must not leave an unsigned
  #     __pycache__ behind. -I ignores the env var, so the explicit -B flag guarantees it;
  #     the export is kept to shield any non-isolated child.
  $env:PYTHONDONTWRITEBYTECODE = "1"

  & $pybin -I -B -m decoy.distribution.verify_extracted $bundleRoot.FullName
  if ($LASTEXITCODE -ne 0) { Die "bundle manifest verification FAILED -- refusing" }
  & $pybin -I -B -m decoy.distribution.selfcheck
  if ($LASTEXITCODE -ne 0) { Die "native companion self-check FAILED -- refusing this install" }

  # Identity check (HIGH): a validly-signed but wrong-version/target bundle served at a
  # pinned URL must NOT be installed as if it were the requested one. Compare the bundle's
  # DECLARED version + target against what was requested, BEFORE any slot is created.
  $binfo = Join-Path $bundleRoot.FullName "BUNDLE_INFO.json"
  if (-not (Test-Path $binfo)) { Die "bundle is missing BUNDLE_INFO.json; cannot verify its identity -- refusing" }
  $info = Get-Content $binfo -Raw | ConvertFrom-Json
  if ($info.target -ne $target) { Die "refusing: bundle declares target '$($info.target)' but this host is '$target' -- nothing installed" }
  if ($ver -ne "local" -and $info.version -ne $ver) { Die "refusing: bundle declares version '$($info.version)' but '$ver' was requested (resolution mismatch) -- versions\$ver left untouched" }

  # First-install-only: the guard above refused any existing runtime, so versions\$ver is
  # absent and this is a plain move into place -- never a destroy-then-replace. The single
  # atomic `current` flip (layout_point) is the only thing that goes live; an interruption
  # before it leaves nothing installed, after it leaves the new runtime live. No move-aside,
  # backup, or restore. (Same-version repair + upgrade are `decoy upgrade`'s job.)
  $dest = Join-Path $versions $ver
  if (Test-Path $dest) { Die "versions\$ver already present -- run 'decoy upgrade --force' to repair; refusing" }
  Move-Item $bundleRoot.FullName $dest
  # Recompute the interpreter path AFTER the move: $pybin pointed into the quarantine dir,
  # which no longer exists once the bundle is placed at $dest.
  $pybin = Join-Path $dest "python\python.exe"
  if (-not (Test-Path $pybin)) { $pybin = Join-Path $dest "python\bin\python.exe" }
  $env:DECOY_HOME = $DecoyHome
  & $pybin -I -B -m decoy.distribution.layout_point $ver
  if ($LASTEXITCODE -ne 0) {
    # Activation failed on a first install: nothing prior was touched, so drop the fresh
    # version dir (leaving `current` absent) and refuse. Nothing to restore.
    Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue
    Die "could not point 'current' at $ver -- nothing installed"
  }

  New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
  # current\decoy is the POSIX launcher; on Windows run the interpreter directly, import-
  # isolated and bytecode-free (-I -B, matching the POSIX launcher): -I stops a planted
  # decoy package in the CWD/PYTHONPATH from shadowing the signed runtime.
  $shim = "@echo off`r`nset PYTHONDONTWRITEBYTECODE=1`r`n`"$DecoyHome\current\python\python.exe`" -I -B -m decoy %*`r`n"
  Set-Content -Path (Join-Path $BinDir "decoy.cmd") -Value $shim -NoNewline

  Info "installed decoy $ver -> $dest"
  Info "launcher: $BinDir\decoy.cmd"
  Info "add $BinDir to your PATH if it is not already, then open a new terminal."
  Info "done. run: decoy --version"
}
finally {
  Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
}
