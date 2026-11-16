@echo off
rem Reclaim a Muse session whose window vanished (dry-run unless -Execute).
rem Usage: recover-muse-session.cmd ^<session-id^> [-Execute]
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\recover-muse-session.ps1" %*
exit /b %errorlevel%
