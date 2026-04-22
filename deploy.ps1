#!/usr/bin/env powershell
# TimeBlock Deployment Script
# Automates Azure deployment and initial configuration

param(
    [Parameter(Mandatory=$false)]
    [string]$Environment = "prod",
    
    [Parameter(Mandatory=$false)]
    [string]$Location = "centralus",
    
    [Parameter(Mandatory=$false)]
    [string]$TeamName = "mtg",
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipAzureDeploy,
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipFunctionDeploy
)

$ErrorActionPreference = "Stop"

Write-Host "🚀 TimeBlock Deployment Script" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host ""

# Verify prerequisites
Write-Host "🔍 Checking prerequisites..." -ForegroundColor Yellow

$requiredCommands = @("az", "func", "python")
foreach ($cmd in $requiredCommands) {
    if (!(Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Error "❌ Required command not found: $cmd"
        exit 1
    }
}

Write-Host "✅ All prerequisites found" -ForegroundColor Green

# Get script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir

# Azure Deployment
if (!$SkipAzureDeploy) {
    Write-Host ""
    Write-Host "🏗️  Deploying Azure infrastructure..." -ForegroundColor Yellow
    
    $resourceGroup = "$TeamName-timeblock-rg"
    
    # Create resource group
    Write-Host "Creating resource group: $resourceGroup" -ForegroundColor Gray
    az group create --name $resourceGroup --location $Location | Out-Null
    
    # Deploy ARM template
    Write-Host "Deploying ARM template..." -ForegroundColor Gray
    $deployment = az deployment group create `
        --resource-group $resourceGroup `
        --template-file "$rootDir/azure-deployment.json" `
        --parameters environment=$Environment teamName=$TeamName location=$Location `
        --query properties.outputs
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error "❌ Azure deployment failed"
        exit 1
    }
    
    # Parse outputs
    $outputs = $deployment | ConvertFrom-Json
    $functionAppName = $outputs.functionAppName.value
    $functionAppUrl = $outputs.functionAppUrl.value
    
    Write-Host "✅ Azure resources deployed" -ForegroundColor Green
    Write-Host "   Function App: $functionAppName" -ForegroundColor Gray
    Write-Host "   URL: $functionAppUrl" -ForegroundColor Gray
    
    # Save deployment info
    $deployInfo = @{
        environment = $Environment
        location = $Location
        resourceGroup = $resourceGroup
        functionAppName = $functionAppName
        functionAppUrl = $functionAppUrl
        deployedAt = (Get-Date -Format "o")
    } | ConvertTo-Json
    
    $deployInfo | Out-File "$rootDir/.deployment.json"
} else {
    Write-Host "⏭️  Skipping Azure deployment (using existing resources)" -ForegroundColor Gray
    
    # Load existing deployment info
    if (Test-Path "$rootDir/.deployment.json") {
        $deployInfo = Get-Content "$rootDir/.deployment.json" | ConvertFrom-Json
        $functionAppName = $deployInfo.functionAppName
        $functionAppUrl = $deployInfo.functionAppUrl
    } else {
        Write-Error "❌ No deployment info found. Run without -SkipAzureDeploy first."
        exit 1
    }
}

# Function App Deployment
if (!$SkipFunctionDeploy) {
    Write-Host ""
    Write-Host "📦 Deploying Azure Function code..." -ForegroundColor Yellow
    
    $funcDir = "$rootDir/azure-function"
    
    if (!(Test-Path $funcDir)) {
        Write-Error "❌ Azure Function directory not found: $funcDir"
        exit 1
    }
    
    Push-Location $funcDir
    
    try {
        # Install dependencies
        Write-Host "Installing dependencies..." -ForegroundColor Gray
        if (!(Test-Path ".venv")) {
            python -m venv .venv
        }
        .\.venv\Scripts\Activate.ps1
        pip install -q -r requirements.txt
        
        # Deploy
        Write-Host "Publishing to Azure..." -ForegroundColor Gray
        func azure functionapp publish $functionAppName --force
        
        if ($LASTEXITCODE -ne 0) {
            Write-Error "❌ Function deployment failed"
            exit 1
        }
        
        Write-Host "✅ Azure Function deployed" -ForegroundColor Green
    } finally {
        Pop-Location
    }
} else {
    Write-Host "⏭️  Skipping Function deployment" -ForegroundColor Gray
}

# Configuration Update
Write-Host ""
Write-Host "📝 Updating configuration..." -ForegroundColor Yellow

$configPath = "$rootDir/config.json"
if (Test-Path $configPath) {
    $config = Get-Content $configPath | ConvertFrom-Json
    
    # Add/update timeblock section
    if (!$config.timeblock) {
        $config | Add-Member -NotePropertyName "timeblock" -NotePropertyValue @{
            enabled = $true
            default_strategy = "aggressive"
            rebalance = @{
                enabled = $true
                min_meeting_minutes = 30
                webhook_url = "$functionAppUrl/api/webhook"
            }
        }
    } else {
        $config.timeblock.rebalance.webhook_url = "$functionAppUrl/api/webhook"
        $config.timeblock.rebalance.enabled = $true
    }
    
    # Save with nice formatting
    $config | ConvertTo-Json -Depth 10 | Out-File $configPath
    
    Write-Host "✅ Configuration updated: $configPath" -ForegroundColor Green
} else {
    Write-Warning "⚠️  Config file not found at $configPath"
}

# Next Steps
Write-Host ""
Write-Host "✨ Deployment Complete!" -ForegroundColor Green
Write-Host "=====================" -ForegroundColor Green
Write-Host ""
Write-Host "📋 Next Steps:" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. 🔄 Register Graph Webhook:" -ForegroundColor Yellow
Write-Host "   python -m work_context_sync.app timeblock today --preview"
Write-Host ""
Write-Host "2. 📱 Set up Power Automate:" -ForegroundColor Yellow
Write-Host "   Follow power-automate/README.md to create Teams notification flows"
Write-Host ""
Write-Host "3. 🧪 Test the system:" -ForegroundColor Yellow
Write-Host "   python -m work_context_sync.app timeblock today --preview"
Write-Host "   python -m work_context_sync.app timeblock today --apply"
Write-Host ""
Write-Host "🔗 Resources:" -ForegroundColor Cyan
Write-Host "   Function App: $functionAppUrl" -ForegroundColor Gray
Write-Host "   Documentation: docs/TIMEBLOCK.md" -ForegroundColor Gray
Write-Host ""
Write-Host "💰 Estimated monthly cost: ~$2-5" -ForegroundColor Green
Write-Host ""
