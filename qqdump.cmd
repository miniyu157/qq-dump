@echo off
rem Windows launcher, same order as qqdump: system Python first, then the interpreter found by uv.
rem uv runs in the repo directory so that its .venv is preferred. Kept ASCII because cmd parses
rem batch files in the console code page.
setlocal
set "SCRIPT_DIR=%~dp0"
set "PYTHON="

rem Probe with -c to skip the Microsoft Store python.exe placeholder.
py -c "" >nul 2>&1 && set "PYTHON=py"
if not defined PYTHON python -c "" >nul 2>&1 && set "PYTHON=python"
if not defined PYTHON for /f "usebackq delims=" %%I in (`uv --directory "%SCRIPT_DIR%." python find 2^>nul`) do set "PYTHON=%%I"
if not defined PYTHON (
    echo Python not found, and uv could not find an interpreter either. 1>&2
    exit /b 1
)

"%PYTHON%" "%SCRIPT_DIR%main.py" %*
exit /b %errorlevel%
