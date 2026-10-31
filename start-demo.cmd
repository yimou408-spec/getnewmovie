@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto dependencies
where py >nul 2>nul
if errorlevel 1 goto usepython
py -3 -m venv .venv
if errorlevel 1 goto failed
goto dependencies
:usepython
python -m venv .venv
if errorlevel 1 goto failed
:dependencies
".venv\Scripts\python.exe" -m pip install -r requirements-s0.txt --disable-pip-version-check
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m scripts.movie_demo %*
if errorlevel 1 goto failed
exit /b 0
:failed
echo Demo could not start. Read the error above. Python 3.11+ and Node.js are required.
pause
exit /b 1
