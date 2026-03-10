@echo off
REM Twitter Agent Launcher - Activates venv and runs the agent
REM Usage: twitter-agent.bat "<twitter task>" [max_steps]

setlocal enabledelayedexpansion

REM Get the directory where this batch file is located
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM Check if venv exists
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo Please run: python run_agent.py "x.com" "test" 0
    echo This will create the venv automatically.
    pause
    exit /b 1
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Check if task argument is provided
if "%~1"=="" (
    echo Usage: twitter-agent.bat "<twitter task>" [max_steps]
    echo.
    echo Examples:
    echo   twitter-agent.bat "search for AI accounts and follow 10" 0
    echo   twitter-agent.bat "post a tweet about crypto" 0
    echo   twitter-agent.bat "find crypto tweets and like 5 of them" 0
    echo.
    pause
    exit /b 1
)

REM Get task and steps
set "TASK=%~1"
set "STEPS=%~2"

REM Default to unlimited steps if not provided
if "%STEPS%"=="" set "STEPS=0"

REM Run the agent
echo Starting Twitter Agent...
echo Task: %TASK%
echo Steps: %STEPS%
echo.

python run_agent.py "x.com" "%TASK%" %STEPS%

REM Deactivate venv
deactivate

echo.
echo Agent finished.
pause
