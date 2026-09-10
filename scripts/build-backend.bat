@echo off
setlocal EnableExtensions

set "ROOT=%~dp0.."
set "BACKEND=%ROOT%\backend"
set "SPEC=%ROOT%\scripts\backend.spec"
set "DIST=%BACKEND%\dist\SuperStationBackend.exe"
set "WORK=%BACKEND%\build"

if not exist "%BACKEND%\run_backend.py" (
    echo ERROR: %BACKEND%\run_backend.py not found.
    exit /b 1
)

if not exist "%SPEC%" (
    echo ERROR: %SPEC% not found.
    exit /b 1
)

echo ========================================
echo Super Station Studio Backend Builder
echo ========================================
echo.

echo Cleaning old PyInstaller output...
if exist "%WORK%" rmdir /s /q "%WORK%"
if exist "%BACKEND%\dist" rmdir /s /q "%BACKEND%\dist"

cd /d "%ROOT%"
set "SSS_PROJECT_ROOT=%ROOT%"
python -m PyInstaller --clean --noconfirm --distpath "%BACKEND%\dist" --workpath "%WORK%" "%SPEC%"
if errorlevel 1 (
    echo.
    echo BUILD FAILED: PyInstaller returned an error.
    exit /b 1
)

if not exist "%DIST%" (
    echo.
    echo BUILD FAILED: expected backend executable was not created:
    echo %DIST%
    exit /b 1
)

echo.
echo BUILD SUCCESSFUL
echo EXE: %DIST%
endlocal
exit /b 0
