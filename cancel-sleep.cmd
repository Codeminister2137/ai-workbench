@echo off
powershell.exe -NoProfile -NonInteractive -File "%~dp0scripts\workstation-sleep.ps1" -CancelAll
exit /b %errorlevel%
