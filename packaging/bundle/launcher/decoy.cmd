@echo off
rem Decoy managed-runtime launcher (Windows shim).
rem
rem Installed inside a versioned bundle at <bundle>\bin\decoy.cmd and reached
rem through a shim on PATH. It resolves its own location so it runs the
rem interpreter of the installed version, and sets DECOY_MANAGED_RUNTIME=1 before
rem handing off (see the posix launcher for why the marker matters: it turns a
rem missing or broken native companion into a loud refusal, not a silent slow
rem path). %~dp0 is this script's directory (…\bin\); the bundle root is its
rem parent and the private venv interpreter sits under it.
setlocal
set "BIN_DIR=%~dp0"
for %%I in ("%BIN_DIR%..") do set "BUNDLE_DIR=%%~fI"
set "VENV_PYTHON=%BUNDLE_DIR%\venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" (
    echo decoy: managed runtime is corrupt: no interpreter at "%VENV_PYTHON%".>&2
    echo decoy: reinstall with "decoy upgrade" or the install script.>&2
    exit /b 1
)
set "DECOY_MANAGED_RUNTIME=1"
"%VENV_PYTHON%" -m decoy %*
exit /b %ERRORLEVEL%
