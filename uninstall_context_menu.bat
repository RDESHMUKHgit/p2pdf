@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo   Uninstalling P2PDF Windows File Explorer Context Menu
echo ============================================================
echo.

set "REG_KEY=HKCU\Software\Classes\*\shell\CreatePDF_P2PDF"
set "SENDTO_SHORTCUT=%APPDATA%\Microsoft\Windows\SendTo\Create PDF with P2PDF.lnk"

echo [1/2] Removing context menu registry entry...
reg query "%REG_KEY%" >nul 2>&1
if %errorlevel% equ 0 (
    reg delete "%REG_KEY%" /f >nul 2>&1
    if %errorlevel% equ 0 (
        echo       Removed registry key: %REG_KEY%
    ) else (
        echo [WARNING] Could not delete registry key %REG_KEY%
    )
) else (
    echo       Context menu registry entry was not found - already uninstalled.
)

echo [2/2] Removing SendTo shortcut...
if exist "%SENDTO_SHORTCUT%" (
    del /q "%SENDTO_SHORTCUT%" >nul 2>&1
    echo       Removed: "%SENDTO_SHORTCUT%"
) else (
    echo       SendTo shortcut was not found.
)

echo.
echo ============================================================
echo   UNINSTALLATION COMPLETE
echo ============================================================
echo.
echo The P2PDF context-menu integration has been successfully removed.
echo Note: Your existing project files, PDFs, and installed binaries were left intact.
echo.
endlocal
exit /b 0
