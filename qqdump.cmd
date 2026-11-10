@echo off
rem Windows launcher, same order as qqdump: QQDUMP_PYTHON, repo .venv, py, python, then uv.
rem Only locates an interpreter (3.11+); dependencies are checked by the program when needed.
rem Kept ASCII because cmd parses batch files in the console code page.
setlocal
set "SCRIPT_DIR=%~dp0"
set "CHECK=import sys; sys.exit(sys.version_info < (3, 11))"

rem exit /b inside a parenthesized block loses the exit code for callers, so branch with goto.
if not defined QQDUMP_PYTHON goto probe
set "PYTHON=%QQDUMP_PYTHON%"
"%PYTHON%" -c "%CHECK%" >nul 2>&1 && goto run
echo QQDUMP_PYTHON is unusable or older than 3.11: %PYTHON% 1>&2
exit /b 1

:probe
rem Running a check also skips the Microsoft Store python.exe placeholder.
set "PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe"
if exist "%PYTHON%" "%PYTHON%" -c "%CHECK%" >nul 2>&1 && goto run
set "PYTHON=py"
py -c "%CHECK%" >nul 2>&1 && goto run
set "PYTHON=python"
python -c "%CHECK%" >nul 2>&1 && goto run
set "PYTHON="
for /f "usebackq delims=" %%I in (`uv --directory "%SCRIPT_DIR%." python find ">=3.11" 2^>nul`) do set "PYTHON=%%I"
if defined PYTHON "%PYTHON%" -c "%CHECK%" >nul 2>&1 && goto run

echo Python 3.11+ not found. Install it, or set QQDUMP_PYTHON to an interpreter. 1>&2
exit /b 1

:run
"%PYTHON%" "%SCRIPT_DIR%main.py" %*
exit /b %errorlevel%
