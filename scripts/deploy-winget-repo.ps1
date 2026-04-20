#!/usr/bin/env pwsh
#Requires -Version 7.0
<#
.SYNOPSIS
    Deploy winget repository to Azure Static Web Apps
.DESCRIPTION
    Deploys the winget REST API source to Azure Static Web Apps
    for private team distribution.
.PARAMETER ResourceGroup
    Azure resource group name (will create if doesn't exist)
.PARAMETER Name
    Static Web App name
.PARAMETER Location
    Azure region (default: centralus)
.PARAMETER Token
    Deployment token (optional - will get from Azure if not provided)
.EXAMPLE
    .\deploy-winget-repo.ps1 -Name "mtg-tools" -ResourceGroup "mtg-rg"
    Deploy to new or existing SWA
.EXAMPLE
    .\deploy-winget-repo.ps1 -Name "mtg-tools" -Token "<deployment-token>"
    Deploy using existing token (for CI/CD)
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Name,
    
    [Parameter(Mandatory)]
    [string]$ResourceGroup,
    
    [string]$Location = "centralus",
    
    [string]$Token = "",
    
    [switch]$SkipBuild,
    
    [switch]$UpdateSha256
)

$ErrorActionPreference = "Stop"

$RepoDir = Join-Path $PSScriptRoot ".." "winget-repo"
$ArtifactDir = Join-Path $RepoDir "_site"

Write-Host "Winget Repository Deployment" -ForegroundColor Cyan
Write-Host "===========================" -ForegroundColor Cyan
Write-Host "Name: $Name" -ForegroundColor Gray
Write-Host "Resource Group: $ResourceGroup" -ForegroundColor Gray
Write-Host "Location: $Location" -ForegroundColor Gray
Write-Host ""

# ============================================================================
# Step 1: Check Azure CLI
# ============================================================================
Write-Host "[1/5] Checking Azure CLI..." -ForegroundColor Yellow

$az = Get-Command az -ErrorAction SilentlyContinue
if (-not $az) {
    Write-Error "Azure CLI not found. Install from https://aka.ms/installazurecliwindows"
    exit 1
}

# Check login
$account = az account show --query "name" -o tsv 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Logging in to Azure..." -ForegroundColor Yellow
    az login
}

Write-Host "✓ Azure CLI ready" -ForegroundColor Green

# ============================================================================
# Step 2: Update SHA256 (if MSI available)
# ============================================================================
if ($UpdateSha256) {
    Write-Host "`n[2/5] Updating SHA256 hashes..." -ForegroundColor Yellow
    
    $MsiPath = Join-Path $PSScriptRoot ".." "dist" "work-context-sync.msi"
    if (Test-Path $MsiPath) {
        $sha256 = (Get-FileHash -Path $MsiPath -Algorithm SHA256).Hash
        Write-Host "  MSI SHA256: $sha256" -ForegroundColor Gray
        
        # Update in all manifest files
        $ManifestFiles = Get-ChildItem -Path $RepoDir -Recurse -Include "*.json", "*.yaml"
        foreach ($file in $ManifestFiles) {
            $content = Get-Content $file -Raw
            if ($content -match "PLACEHOLDER_SHA256") {
                $content = $content -replace "PLACEHOLDER_SHA256", $sha256
                Set-Content -Path $file -Value $content -NoNewline
                Write-Host "  Updated: $($file.Name)" -ForegroundColor Gray
            }
        }
        Write-Host "✓ SHA256 updated" -ForegroundColor Green
    } else {
        Write-Warning "MSI not found at $MsiPath - skipping SHA256 update"
    }
} else {
    Write-Host "`n[2/5] Skipping SHA256 update (use -UpdateSha256 to update)" -ForegroundColor Gray
}

# ============================================================================
# Step 3: Build/prepare site
# ============================================================================
if (-not $SkipBuild) {
    Write-Host "`n[3/5] Preparing site..." -ForegroundColor Yellow
    
    # Clean previous build
    if (Test-Path $ArtifactDir) {
        Remove-Item -Recurse -Force $ArtifactDir
    }
    
    # Copy all files to _site
    New-Item -ItemType Directory -Path $ArtifactDir -Force | Out-Null
    
    # Copy manifest files
    Copy-Item -Path (Join-Path $RepoDir "index.json") -Destination $ArtifactDir
    Copy-Item -Path (Join-Path $RepoDir "source.json") -Destination $ArtifactDir
    Copy-Item -Path (Join-Path $RepoDir "staticwebapp.config.json") -Destination $ArtifactDir
    
    # Copy package manifests
    New-Item -ItemType Directory -Path (Join-Path $ArtifactDir "packageManifests") -Force | Out-Null
    Copy-Item -Path (Join-Path $RepoDir "packageManifests\*") -Destination (Join-Path $ArtifactDir "packageManifests") -Recurse
    
    # Copy multi-file manifests
    New-Item -ItemType Directory -Path (Join-Path $ArtifactDir "manifests") -Force | Out-Null
    Copy-Item -Path (Join-Path $RepoDir "manifests\*") -Destination (Join-Path $ArtifactDir "manifests") -Recurse
    
    Write-Host "✓ Site prepared: $ArtifactDir" -ForegroundColor Green
} else {
    Write-Host "`n[3/5] Skipping site preparation (-SkipBuild)" -ForegroundColor Gray
}

# ============================================================================
# Step 4: Create/verify Static Web App
# ============================================================================
Write-Host "`n[4/5] Verifying Azure Static Web App..." -ForegroundColor Yellow

# Check if resource group exists
$rgExists = az group exists --name $ResourceGroup --query "@" -o tsv
if ($rgExists -eq "false") {
    Write-Host "  Creating resource group: $ResourceGroup" -ForegroundColor Gray
    az group create --name $ResourceGroup --location $Location | Out-Null
}

# Check if SWA exists
$swaExists = az staticwebapp show --name $Name --resource-group $ResourceGroup --query "name" -o tsv 2>$null
if (-not $swaExists) {
    Write-Host "  Creating Static Web App: $Name" -ForegroundColor Gray
    
    # Create without GitHub (manual deployment)
    $result = az staticwebapp create `
        --name $Name `
        --resource-group $ResourceGroup `
        --location $Location `
        --sku Free `
        --no-wait `
        2>&1
    
    Write-Host "  Waiting for provisioning..." -ForegroundColor Gray
    Start-Sleep -Seconds 10
    
    # Get deployment token
    $Token = az staticwebapp secrets list --name $Name --resource-group $ResourceGroup --query "properties.apiKey" -o tsv
} else {
    Write-Host "  Static Web App exists: $Name" -ForegroundColor Gray
    
    if (-not $Token) {
        Write-Host "  Fetching deployment token..." -ForegroundColor Gray
        $Token = az staticwebapp secrets list --name $Name --resource-group $ResourceGroup --query "properties.apiKey" -o tsv
    }
}

if (-not $Token) {
    Write-Error "Failed to get deployment token"
    exit 1
}

# Get hostname
$hostname = az staticwebapp show --name $Name --resource-group $ResourceGroup --query "defaultHostname" -o tsv
Write-Host "  Hostname: $hostname" -ForegroundColor Gray

Write-Host "✓ Static Web App ready" -ForegroundColor Green

# ============================================================================
# Step 5: Deploy
# ============================================================================
Write-Host "`n[5/5] Deploying..." -ForegroundColor Yellow

# Use SWA CLI if available, otherwise use zip deploy
$swa = Get-Command swa -ErrorAction SilentlyContinue
if ($swa) {
    Write-Host "  Using SWA CLI..." -ForegroundColor Gray
    & $swa.Source deploy `
        --app-location $ArtifactDir `
        --deployment-token $Token `
        --env production
} else {
    Write-Host "  Using ZIP deploy..." -ForegroundColor Gray
    
    # Create zip
    $ZipPath = Join-Path $env:TEMP "winget-repo.zip"
    if (Test-Path $ZipPath) {
        Remove-Item $ZipPath -Force
    }
    
    Push-Location $ArtifactDir
    try {
        Compress-Archive -Path "*" -DestinationPath $ZipPath -Force
    } finally {
        Pop-Location
    }
    
    # Deploy via REST API
    $headers = @{
        "Authorization" = "Bearer $Token"
        "Content-Type" = "application/octet-stream"
    }
    
    Invoke-RestMethod `
        -Uri "https://$hostname/api/zipdeploy" `
        -Method Post `
        -Headers $headers `
        -InFile $ZipPath
}

Write-Host "✓ Deployment complete" -ForegroundColor Green

# ============================================================================
# Summary
# ============================================================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Winget Repository Deployed!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "URL: https://$hostname" -ForegroundColor White
Write-Host "`nAdd to winget:" -ForegroundColor Yellow
Write-Host "  winget source add -n mtg-tools -a https://$hostname" -ForegroundColor Gray
Write-Host "`nInstall package:" -ForegroundColor Yellow
Write-Host "  winget install --source mtg-tools MidtownTechnologyGroup.WorkContextSync" -ForegroundColor Gray
Write-Host "`nTeam setup:" -ForegroundColor Yellow
Write-Host "  See: pages/reference.runbooks.work-context-sync-team-setup.md" -ForegroundColor Gray
