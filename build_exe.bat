@echo off
rem ============================================================
rem  Build Study Helper into standalone exe + one-click installer
rem  Output:
rem    dist\StudyHelper\StudyHelper.exe   (main program folder)
rem    dist\StudyHelper-Setup.exe         (installer, double-click it)
rem  Note: keep this file ASCII-only (cmd uses GBK for .bat files)
rem ============================================================

rem Note: crawler uses Playwright - it falls back to the system
rem Microsoft Edge automatically, so no browser download needed.

echo [1/2] Building main program (StudyHelper.exe) ...
python -m PyInstaller --noconfirm --clean --noconsole --name StudyHelper ^
  --add-data "templates;templates" --add-data "static;static" ^
  --collect-data jieba ^
  app.py
if errorlevel 1 goto :fail

echo [2/2] Building installer (StudyHelper-Setup.exe) ...
python -m PyInstaller --noconfirm --clean --noconsole --onefile ^
  --name "StudyHelper-Setup" ^
  --add-data "dist\StudyHelper;app" ^
  install_app.py
if errorlevel 1 goto :fail

echo.
echo ============================================================
echo  Build finished!
echo    Main program : dist\StudyHelper\StudyHelper.exe
echo    Installer    : dist\StudyHelper-Setup.exe
echo    Share the installer with your friends - they just
echo    double-click it, pick a folder, done. Desktop shortcut
echo    is created automatically.
echo ============================================================
pause
exit /b 0

:fail
echo.
echo Build FAILED. Scroll up to see the error message.
pause
exit /b 1
