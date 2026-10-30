@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo   Building P2PDF - Standalone Windows Executable
echo ===================================================

:: Check Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    exit /b 1
)

:: Install required dependencies
echo [1/5] Checking and installing dependencies...
if exist "requirements-dev.txt" (
    python -m pip install -r requirements-dev.txt
) else (
    python -m pip install -r requirements.txt
)
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    exit /b 1
)

:: Generate / sync Windows version resource metadata
echo [2/5] Generating Windows version resource metadata...
python generate_version_info.py
if %errorlevel% neq 0 (
    echo [ERROR] Failed to generate Windows version resource metadata.
    exit /b 1
)

:: Clean previous build artifacts
echo [3/5] Cleaning previous build artifacts...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "P2PDF.spec" del /q "P2PDF.spec"

:: Build executable with PyInstaller
echo [4/5] Compiling P2PDF.exe with PyInstaller...
python -m PyInstaller ^
    --onefile ^
    --noconsole ^
    --name P2PDF ^
    --version-file version_info.txt ^
    --clean ^
    main.py

if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller build failed.
    exit /b 1
)

:: Verify output executable
echo [5/5] Verifying executable...
if exist "dist\P2PDF.exe" (
    echo.
    echo ===================================================
    echo   BUILD SUCCESSFUL!
    echo   Executable: %CD%\dist\P2PDF.exe
    echo ===================================================
) else (
    echo [ERROR] dist\P2PDF.exe was not created.
    exit /b 1
)

endlocal
