@echo off
rem Stop Study Helper (kill the StudyHelper.exe or python app.py process)
rem Note: keep this file ASCII-only (no Chinese) to avoid cmd encoding issues.
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -like 'StudyHelper*') -or ($_.Name -eq 'python.exe' -and $_.CommandLine -like '*app.py*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Study Helper stopped. You can close this window.
pause
