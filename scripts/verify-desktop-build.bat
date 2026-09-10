@echo off
setlocal
set "ROOT=%~dp0.."
set "BACKEND_EXE=%ROOT%\backend\dist\SuperStationBackend.exe"
set "FRONTEND_INDEX=%ROOT%\frontend\dist\index.html"

echo Checking Super Station Studio desktop build inputs...
if not exist "%BACKEND_EXE%" (
  echo ERROR: Missing %BACKEND_EXE%
  echo Run scripts\build-backend.bat first.
  exit /b 1
)
if not exist "%FRONTEND_INDEX%" (
  echo ERROR: Missing %FRONTEND_INDEX%
  echo Run npm run frontend:build first.
  exit /b 1
)
echo OK: backend executable and frontend build are present.
endlocal
exit /b 0
