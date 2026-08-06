$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = $ws.CreateShortcut("$desktop\学习助手Pro.lnk")
$lnk.TargetPath = "wscript.exe"
$lnk.Arguments = '"D:\vscode\study-helper\启动学习助手.vbs"'
$lnk.WorkingDirectory = "D:\vscode\study-helper"
$lnk.Description = "学习助手 Pro - 双击启动（无黑窗口），用「停止学习助手」关闭"
$lnk.Save()
Write-Host "OK"
