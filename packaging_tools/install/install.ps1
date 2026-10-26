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

  $versions = Join-Path $DecoyHome "versions"
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
  # pinned URL must NOT overwrite the retained versions\<version> runtime. Compare the
  # bundle's DECLARED version + target against what was requested, BEFORE any deletion.
  $binfo = Join-Path $bundleRoot.FullName "BUNDLE_INFO.json"
  if (-not (Test-Path $binfo)) { Die "bundle is missing BUNDLE_INFO.json; cannot verify its identity -- refusing" }
  $info = Get-Content $binfo -Raw | ConvertFrom-Json
  if ($info.target -ne $target) { Die "refusing: bundle declares target '$($info.target)' but this host is '$target' -- nothing installed" }
  if ($ver -ne "local" -and $info.version -ne $ver) { Die "refusing: bundle declares version '$($info.version)' but '$ver' was requested (resolution mismatch) -- versions\$ver left untouched" }

  # Promote stage-beside, never destroy-then-replace (mirror install.sh and the Python
  # installer): the existing runtime is NEVER removed before the replacement is in place.
  # A same-version repair moves the original ASIDE as a retained backup, moves the
  # replacement in, points `current`, then reclaims the backup; a failure at any step
  # restores the original, so an interrupted re-install of the active version can never
  # leave the host with no working runtime.
  $dest = Join-Path $versions $ver
  $backup = Join-Path $versions (".backup.$ver." + $PID)
  if (Test-Path $backup) { Remove-Item $backup -Recurse -Force }
  if (Test-Path $dest) { Move-Item $dest $backup }
  try {
    Move-Item $bundleRoot.FullName $dest
  } catch {
    if (Test-Path $backup) { Move-Item $backup $dest }
    Die "could not promote the new runtime into versions\$ver -- the previous runtime is intact"
  }
  # Recompute the interpreter path AFTER the move: $pybin pointed into the quarantine dir,
  # which no longer exists once the bundle is promoted to $dest.
  $pybin = Join-Path $dest "python\python.exe"
  if (-not (Test-Path $pybin)) { $pybin = Join-Path $dest "python\bin\python.exe" }
  $env:DECOY_HOME = $DecoyHome
  & $pybin -I -B -m decoy.distribution.layout_point $ver
  if ($LASTEXITCODE -ne 0) {
    # Activation failed: restore the retained original over the unvalidated replacement.
    if (Test-Path $backup) { Remove-Item $dest -Recurse -Force; Move-Item $backup $dest }
    Die "could not point 'current' at $ver -- the previous runtime is intact"
  }
  if (Test-Path $backup) { Remove-Item $backup -Recurse -Force }

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
