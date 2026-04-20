#!/usr/bin/env powershell
# Windows-native work-context-sync runner
# Run this from PowerShell/Windows Terminal (not WSL)

$ErrorActionPreference = "Stop"

# Change to script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# Run sync with device code (easiest for Windows)
Write-Host "Starting work-context sync for today..." -ForegroundColor Cyan
Write-Host ""

python -m work_context_sync.app sync today --config config.json

Write-Host ""
Write-Host "Sync complete. Raw data written to: work-context/raw/graph/" -ForegroundColor Green
