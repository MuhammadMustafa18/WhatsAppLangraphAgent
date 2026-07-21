@echo off
REM ============================================================
REM  Recluze — Full Production Build Script
REM  Produces a Tauri .msi/.exe installer in
REM  desktop\src-tauri\target\release\bundle\
REM ============================================================
setlocal enabledelayedexpansion
set ROOT=%~dp0..
set VENV=%ROOT%\.venv

echo === Step 1: Build Baileys sidecar (Node.js → standalone .exe via bun) ===
cd /d "%ROOT%\baileys-sidecar"
if not exist "node_modules" (
    echo Installing baileys-sidecar dependencies...
    call npm install
)
call npm run build
if %errorlevel% neq 0 exit /b %errorlevel%
call npm run compile
if %errorlevel% neq 0 exit /b %errorlevel%

echo === Step 2: Build Python backend (PyInstaller → recluze-api.exe) ===
cd /d "%ROOT%"
call "%VENV%\Scripts\pip" install pyinstaller -q
if %errorlevel% neq 0 exit /b %errorlevel%
call "%VENV%\Scripts\pyinstaller" scripts\recluze-api.spec --clean
if %errorlevel% neq 0 exit /b %errorlevel%

echo === Step 3: Copy sidecars to Tauri bundle dir ===
mkdir "%ROOT%\desktop\src-tauri\sidecars\python" 2>nul
copy /y "%ROOT%\dist\recluze-api.exe" "%ROOT%\desktop\src-tauri\sidecars\python\recluze-api.exe"
copy /y "%ROOT%\baileys-sidecar\baileys-sidecar.exe" "%ROOT%\desktop\src-tauri\sidecars\baileys-sidecar.exe"

echo === Step 4: Build Tauri app (installer) ===
cd /d "%ROOT%\desktop"
call npm install
call npm run tauri build
if %errorlevel% neq 0 exit /b %errorlevel%

echo === Done! Installer is in desktop\src-tauri\target\release\bundle\ ===
cd /d "%ROOT%"
