@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"
if /i "%PROCESSOR_ARCHITECTURE%"=="AMD64" goto tools
if /i "%PROCESSOR_ARCHITEW6432%"=="AMD64" goto tools
echo This launcher supports Windows 10/11 x64. See docs/local-demo.md for other systems.
goto failed

:tools
set "MOVIE_BOOTSTRAP=%CD%\artifacts\bootstrap"
set "MOVIE_TOOLCHAIN=%CD%\scripts\demo-toolchain.json"
set "UV_CACHE_DIR=%MOVIE_BOOTSTRAP%\cache"
set "UV_PYTHON_INSTALL_DIR=%MOVIE_BOOTSTRAP%\python"
set "UV_PYTHON_BIN_DIR=%MOVIE_BOOTSTRAP%\bin"
set "UV_NO_CONFIG=1"
set "PYTHONUTF8=1"
set "PYTHONPATH="
set "PYTHONHOME="
set "PYTHONNOUSERSITE=1"
set "PSModulePath=%SystemRoot%\System32\WindowsPowerShell\v1.0\Modules"
set "npm_config_cache=%MOVIE_BOOTSTRAP%\npm-cache"
echo [1/4] Preparing project-local tools. No global installation or API keys required.
call scripts\bootstrap-tools.cmd
if errorlevel 1 goto failed
set "MOVIE_UV=%MOVIE_BOOTSTRAP%\uv-0.9.8\uv.exe"
set "PATH=%MOVIE_BOOTSTRAP%\node\node-v24.11.1-win-x64;%CD%\.venv\Scripts;%PATH%"
echo [2/4] Preparing Python 3.13.9 and locked dependencies inside this project.
if exist ".venv\Scripts\python.exe" goto dependencies
"%MOVIE_UV%" venv --python 3.13.9 --managed-python .venv
if errorlevel 1 goto failed
:dependencies
"%MOVIE_UV%" pip install --python ".venv\Scripts\python.exe" --require-hashes --link-mode copy -r requirements-demo.lock
if errorlevel 1 goto failed
echo [3/4] Building the checked-out frontend. The first run also downloads the local model.
echo [4/4] Keep this window open; wait for Local model ready or the rule fallback notice.
".venv\Scripts\python.exe" -m scripts.movie_demo %*
if errorlevel 1 goto failed
exit /b 0
:failed
echo Demo could not start. Check the network and the error above, then double-click again.
echo Completed downloads stay in artifacts. No existing service was stopped.
if not defined MOVIE_DEMO_NONINTERACTIVE pause
exit /b 1
