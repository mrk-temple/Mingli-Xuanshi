@echo off
setlocal
cd /d "%~dp0"
title Mingli XuanShi - local server

REM ---------------------------------------------------------------------------
rem  Mingli XuanShi starter (double-click this file)
rem  Auto-enables the conda env "JNU" where dependencies live, then serves
rem  the web workbench at http://127.0.0.1:8800
REM ---------------------------------------------------------------------------

rem --- try to activate the JNU conda env (deps were installed there) ---
call conda activate JNU >nul 2>&1

rem --- verify dependencies are importable with the active python ---
python -c "import fastapi, uvicorn, jinja2, lunar_python" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [!] Required packages were not found in the current Python.
    echo     Run these once in the JNU env, then double-click again:
    echo.
    echo        conda activate JNU
    echo        pip install fastapi uvicorn jinja2 lunar_python
    echo.
    pause
    exit /b 1
)

rem --- open the browser after a short delay (server needs to be up first) ---
start "" /min cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:8800"

echo.
echo   ==============================================
echo    Mingli XuanShi  命理玄师  is starting ...
echo    Open your browser at  http://127.0.0.1:8800
echo.
echo    The browser opens automatically in a moment.
echo    Press Ctrl+C here to stop the server.
echo   ==============================================
echo.

python -m mingli

echo.
echo   Server stopped.
pause