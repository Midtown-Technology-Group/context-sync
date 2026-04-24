@echo off
REM Windows work-context-sync runner
REM Double-click or run from Command Prompt

cd /d "%~dp0"
echo Starting work-context sync...
set "PYTHONPATH=%~dp0src"
"%~dp0.venv\Scripts\python.exe" -m work_context_sync.app sync today --config config.windows.json
pause
