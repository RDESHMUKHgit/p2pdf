@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo   Installing P2PDF Windows File Explorer Context Menu
echo ============================================================
echo.

:: Resolve absolute directory of this script (independent of current working directory)
set "SCRIPT_DIR=%~dp0"

:: Locate P2PDF.exe
set "SOURCE_EXE="
if exist "%SCRIPT_DIR%dist\P2PDF.exe" (
    set "SOURCE_EXE=%SCRIPT_DIR%dist\P2PDF.exe"
) else if exist "%SCRIPT_DIR%P2PDF.exe" (
    set "SOURCE_EXE=%SCRIPT_DIR%P2PDF.exe"
)

if not defined SOURCE_EXE (
    echo [ERROR] P2PDF.exe was not found in:
    echo         "%SCRIPT_DIR%dist\P2PDF.exe"
    echo.
    echo Please compile the standalone executable first by running:
    echo   build.bat
    echo.
    exit /b 1
)

:: Define per-user stable installation directory
set "INSTALL_DIR=%LOCALAPPDATA%\Programs\P2PDF"
set "INSTALL_EXE=%INSTALL_DIR%\P2PDF.exe"

echo [1/3] Installing executable to user programs directory...
echo       Source: "%SOURCE_EXE%"
echo       Target: "%INSTALL_EXE%"

if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%" 2>nul
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create installation directory: "%INSTALL_DIR%"
        exit /b 1
    )
)

set "COPIED=0"
for /L %%i in (1,1,5) do (
    if !COPIED! equ 0 (
        copy /y "%SOURCE_EXE%" "%INSTALL_EXE%" >nul 2>&1
        if !errorlevel! equ 0 set "COPIED=1"
        if !COPIED! equ 0 timeout /t 1 /nobreak >nul 2>&1
    )
)
if !COPIED! equ 0 (
    echo [ERROR] Failed to copy P2PDF.exe to: "%INSTALL_EXE%"
    echo Please make sure P2PDF is not currently running.
    exit /b 1
)

:: Copy default p2pdf.ini if not already present in install directory (preserves user customizations)
if not exist "%INSTALL_DIR%\p2pdf.ini" (
    if exist "%SCRIPT_DIR%p2pdf.ini" (
        copy /y "%SCRIPT_DIR%p2pdf.ini" "%INSTALL_DIR%\p2pdf.ini" >nul 2>&1
        echo       Created default configuration: "%INSTALL_DIR%\p2pdf.ini"
    )
)

echo [2/3] Registering Windows Explorer context menu verb...

set "REG_KEY=HKCU\Software\Classes\*\shell\CreatePDF_P2PDF"
set "AQS_FILTER=System.FileExtension:=\".jpg\" OR System.FileExtension:=\".jpeg\" OR System.FileExtension:=\".png\" OR System.FileExtension:=\".webp\" OR System.FileName:=\"*.jpg\" OR System.FileName:=\"*.jpeg\" OR System.FileName:=\"*.png\" OR System.FileName:=\"*.webp\""

:: Set verb display text
reg add "%REG_KEY%" /ve /t REG_SZ /d "Create PDF with P2PDF" /f >nul
if %errorlevel% neq 0 goto :reg_error

:: Set MultiSelectModel to Player (handles multiple files in single instance)
reg add "%REG_KEY%" /v "MultiSelectModel" /t REG_SZ /d "Player" /f >nul
if %errorlevel% neq 0 goto :reg_error

:: Set Icon
reg add "%REG_KEY%" /v "Icon" /t REG_SZ /d "\"%INSTALL_EXE%\",0" /f >nul
if %errorlevel% neq 0 goto :reg_error

:: Set AppliesTo filter to supported image formats
reg add "%REG_KEY%" /v "AppliesTo" /t REG_SZ /d "%AQS_FILTER%" /f >nul
if %errorlevel% neq 0 goto :reg_error

:: Set command to launch P2PDF with the selected file (%1)
reg add "%REG_KEY%\command" /ve /t REG_SZ /d "\"%INSTALL_EXE%\" \"%%1\"" /f >nul
if %errorlevel% neq 0 goto :reg_error

echo [3/3] Creating SendTo shortcut for quick access...
set "SENDTO_DIR=%APPDATA%\Microsoft\Windows\SendTo"
if exist "%SENDTO_DIR%" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SENDTO_DIR%\Create PDF with P2PDF.lnk'); $s.TargetPath = '%INSTALL_EXE%'; $s.Save()" >nul 2>&1
)

echo.
echo ============================================================
echo   INSTALLATION SUCCESSFUL!
echo ============================================================
echo.
echo P2PDF is now integrated into Windows File Explorer.
echo.
echo How to use:
echo   1. Select one or more photos (.jpg, .jpeg, .png, .webp).
echo   2. Right-click and choose "Create PDF with P2PDF".
echo      Note: On Windows 11, click "Show more options" (or Shift+F10).
echo   3. A single PDF will be generated in the photo folder.
echo.
echo Installed path: "%INSTALL_EXE%"
echo.
endlocal
exit /b 0

:reg_error
echo.
echo [ERROR] Failed to update Windows Registry entries.
echo Please ensure you have write permissions to HKEY_CURRENT_USER\Software\Classes.
endlocal
exit /b 1
