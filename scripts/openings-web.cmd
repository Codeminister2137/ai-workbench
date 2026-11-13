@echo off
rem Start the Openings web/API on loopback (NOT openings-web: it hardcodes 0.0.0.0).
setlocal
set ROOT=%~dp0..\
set SVC=%ROOT%apps\job_search\openings-svc
set OPENINGS_DATA_DIR=%SVC%\data
set /p OPENINGS_API_TOKEN=<%SVC%\api-token.txt
"%SVC%\.venv\Scripts\python.exe" -m uvicorn openings.web.app:app --host 127.0.0.1 --port 8501
