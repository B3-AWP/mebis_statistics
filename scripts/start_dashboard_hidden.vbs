Set oShell = CreateObject("WScript.Shell")
oShell.Run Chr(34) & WScript.ScriptFullName & "\..\start_dashboard.bat" & Chr(34), 0, False
