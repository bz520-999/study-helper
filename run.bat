@echo off
chcp 65001 >nul
cd /d %~dp0

rem ==== Always run the latest code: stop any existing instance first ====
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -like 'StudyHelper*') -or ($_.Name -eq 'python.exe' -and $_.CommandLine -like '*app.py*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"


rem ==== Check Python ====
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.12:
    echo https://www.python.org/downloads/
    echo Check "Add python.exe to PATH" during install.
    pause
    exit /b 1
)

rem ==== Create venv on first run ====
if not exist venv (
    echo First run: creating virtual environment...
    python -m venv venv
)

rem ==== Activate venv and install dependencies ====
call venv\Scripts\activate.bat
python -m pip install -r requirements.txt --quiet

rem ==== Start the app ====
echo.
echo Study Helper Pro is starting...
echo If the browser does not open, visit: http://127.0.0.1:5000
echo Closing this window = closing the app.
echo.
python app.py

pause
