@echo off
REM Windows work-context-sync runner
REM Double-click or run from Command Prompt

cd /d "%~dp0"
echo Starting work-context sync...
python -m work_context_sync.app sync today --config config.json
pause
