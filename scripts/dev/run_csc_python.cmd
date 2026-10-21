@echo off
rem Runs the Python of the "csc" conda environment with the given arguments:
rem
rem     scripts\dev\run_csc_python.cmd -u scripts/dev/serve_migrated.py --dump latest ...
rem
rem The launch configurations of .claude/launch.json use it, so that no path of
rem a user account stands in a committed file. The environment is looked for in
rem this order, the first that exists wins:
rem   1. CSC_PYTHON            a python.exe you name yourself (any environment)
rem   2. CONDA_PREFIX          the active environment, when it is called csc
rem   3. CONDA_EXE             <conda base>\envs\csc, the base found from conda
rem   4. %USERPROFILE%\miniconda3 (anaconda3, miniforge3, mambaforge) and
rem      %ProgramData%\miniconda3 (anaconda3): the usual install places
rem   5. `conda run -n csc --no-capture-output python` when conda is on the PATH
rem Nothing is installed or changed; with no environment found it says so and
rem stops with exit code 1.
setlocal EnableDelayedExpansion
set "PYEXE="

if defined CSC_PYTHON if exist "%CSC_PYTHON%" set "PYEXE=%CSC_PYTHON%"

if not defined PYEXE if defined CONDA_PREFIX (
  for %%I in ("%CONDA_PREFIX%") do (
    if /I "%%~nxI"=="csc" if exist "%CONDA_PREFIX%\python.exe" set "PYEXE=%CONDA_PREFIX%\python.exe"
  )
)

if not defined PYEXE if defined CONDA_EXE (
  for %%I in ("%CONDA_EXE%") do set "CONDA_DIR=%%~dpI"
  for %%I in ("!CONDA_DIR!..") do set "CONDA_BASE=%%~fI"
  if exist "!CONDA_BASE!\envs\csc\python.exe" set "PYEXE=!CONDA_BASE!\envs\csc\python.exe"
)

if not defined PYEXE (
  for %%D in (miniconda3 anaconda3 miniforge3 mambaforge) do (
    if not defined PYEXE if exist "%USERPROFILE%\%%D\envs\csc\python.exe" set "PYEXE=%USERPROFILE%\%%D\envs\csc\python.exe"
  )
)

if not defined PYEXE if defined ProgramData (
  for %%D in (miniconda3 anaconda3) do (
    if not defined PYEXE if exist "%ProgramData%\%%D\envs\csc\python.exe" set "PYEXE=%ProgramData%\%%D\envs\csc\python.exe"
  )
)

if defined PYEXE goto run_python

where conda >nul 2>nul
if errorlevel 1 goto not_found
conda run -n csc --no-capture-output python %*
exit /b %ERRORLEVEL%

:run_python
"%PYEXE%" %*
exit /b %ERRORLEVEL%

:not_found
echo run_csc_python.cmd: no conda environment "csc" found. 1>&2
echo Create it, or set CSC_PYTHON to the python.exe to use. 1>&2
exit /b 1
