@echo off
rem Scheduled-task entry for the dashboard redeploy supervisor.
rem schtasks /tr is limited to 261 chars, so the task calls this wrapper.
set ROOT=%~dp0..
"%ROOT%\.venv\Scripts\python.exe" "%ROOT%\apps\workbench_dashboard\dashboard_supervise.py" --main-root "%ROOT%" --data-dir "%ROOT%\apps\workbench_dashboard\data" --config "%ROOT%\apps\workbench_dashboard\dashboard.json" --port 8766 --serve-branch develop %*
