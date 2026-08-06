' Launch Study Helper silently (no black console window)
' Double-click this file (or the desktop shortcut) to start the app.
Set fso = CreateObject("Scripting.FileSystemObject")
baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
Set ws = CreateObject("WScript.Shell")
cmdLine = "cmd /c ""cd /d """ & baseDir & """ && call """ & baseDir & "\run.bat"""
ws.Run cmdLine, 0, False
