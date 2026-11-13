@echo off
rem One Openings collection run (called by the OpeningsCollect scheduled task).
setlocal
set ROOT=%~dp0..\
set SVC=%ROOT%apps\job_search\openings-svc
set OPENINGS_DATA_DIR=%SVC%\data
"%SVC%\.venv\Scripts\openings.exe" run
