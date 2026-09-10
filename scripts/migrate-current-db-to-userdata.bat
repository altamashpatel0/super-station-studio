@echo off
setlocal

cd /d "%~dp0.."

echo.
echo Super Station Studio - migrate current library to this Windows user
echo.

if not exist "backend\data\library.db" (
  echo ERROR: backend\data\library.db was not found.
  echo Nothing was migrated.
  exit /b 1
)

set "TARGET=%APPDATA%\super-station-studio\data"
if not exist "%TARGET%" mkdir "%TARGET%"

if exist "%TARGET%\library.db" (
  echo Target database already exists:
  echo %TARGET%\library.db
  echo No overwrite was performed.
  exit /b 2
)

copy /Y "backend\data\library.db" "%TARGET%\library.db"

if errorlevel 1 (
  echo ERROR: database copy failed.
  exit /b 1
)

echo.
echo SUCCESS.
echo Database copied to:
echo %TARGET%\library.db
echo.
echo This is a ONE-TIME migration for the current PC/user.
echo Future packaged launches will use this persistent database.
exit /b 0
