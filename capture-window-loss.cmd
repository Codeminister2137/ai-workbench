@echo off
rem One-click evidence capture for a vanished Muse/PowerShell window.
rem Usage: capture-window-loss.cmd [session-id]
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\capture-window-loss.ps1" %*
exit /b %errorlevel%
