@echo off
REM ============================================================
REM  Recluze — Local Test Build (no GitHub upload)
REM
REM  Builds both sidecars and the Tauri installer into the
REM  standard release/bundle/ path. Test the resulting installers
REM  locally before running scripts\build_release.bat + a release
REM  script for GitHub.
REM
REM  Does NOT bump versions, does NOT touch the GitHub release,
REM  does NOT change tauri.conf.json.
REM ============================================================
setlocal enabledelayedexpansion
set ROOT=%~dp0..
set VENV=%ROOT%\.venv

echo === Step 1: Build Baileys sidecar ===
cd /d "%ROOT%\baileys-sidecar"
if not exist "node_modules" (
    echo Installing baileys-sidecar dependencies...
    call npm install
)
call npm run build
if %errorlevel% neq 0 exit /b %errorlevel%
call bun build --compile ./dist/index.js --outfile baileys-sidecar
if %errorlevel% neq 0 exit /b %errorlevel%

echo === Step 2: Build Python backend ===
cd /d "%ROOT%"
call "%VENV%\Scripts\pip" install pyinstaller -q
if %errorlevel% neq 0 exit /b %errorlevel%
call "%VENV%\Scripts\pyinstaller" scripts\recluze-api.spec --clean
if %errorlevel% neq 0 exit /b %errorlevel%

echo === Step 3: Copy sidecars to Tauri bundle dir ===
mkdir "%ROOT%\desktop\src-tauri\sidecars\python" 2>nul
copy /y "%ROOT%\dist\recluze-api.exe" "%ROOT%\desktop\src-tauri\sidecars\python\recluze-api.exe"
copy /y "%ROOT%\baileys-sidecar\baileys-sidecar.exe" "%ROOT%\desktop\src-tauri\sidecars\baileys-sidecar.exe"

echo === Step 4: Build Tauri installer ===
cd /d "%ROOT%\desktop"
call npm install
call npm run tauri build
if %errorlevel% neq 0 exit /b %errorlevel%

echo.
echo === Done! Test installers at: ===
echo   %ROOT%\desktop\src-tauri\target\release\bundle\msi\Recluze_0.1.0_x64_en-US.msi
echo   %ROOT%\desktop\src-tauri\target\release\bundle\nsis\Recluze_0.1.0_x64-setup.exe
echo.
echo Filename still says 0.1.0 because we did not bump the version.
echo Install one, smoke-test, then run the release script to publish.
cd /d "%ROOT%"
