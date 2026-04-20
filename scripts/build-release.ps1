#!/usr/bin/env pwsh
#Requires -Version 7.0
<#
.SYNOPSIS
    Build all release artifacts for work-context-sync
.DESCRIPTION
    Creates wheel, executable, and MSI installer for distribution.
    Run this locally before pushing to GitHub for full release.
.PARAMETER Version
    Version number for the release (e.g., "1.0.0")
.PARAMETER SkipExe
    Skip PyInstaller executable build (faster for testing)
.PARAMETER SkipMsi
    Skip MSI build (requires WiX)
.EXAMPLE
    .\build-release.ps1 -Version "1.0.0"
    Full build with all artifacts
.EXAMPLE
    .\build-release.ps1 -Version "1.0.0" -SkipMsi
    Build wheel and exe only (no MSI)
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Version,
    [switch]$SkipExe,
    [switch]$SkipMsi
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "Continue"

# Paths
$Root = Split-Path $PSScriptRoot -Parent
$DistDir = Join-Path $Root "dist"
$ArtifactDir = Join-Path $DistDir "artifacts"

# Ensure directories exist
New-Item -ItemType Directory -Path $DistDir -Force | Out-Null
New-Item -ItemType Directory -Path $ArtifactDir -Force | Out-Null

Write-Host "Building Work Context Sync v$Version" -ForegroundColor Cyan
Write-Host "Output: $ArtifactDir" -ForegroundColor Gray

# ============================================================================
# Step 1: Python Wheel
# ============================================================================
Write-Host "`n[1/4] Building Python wheel..." -ForegroundColor Yellow

Push-Location $Root
try {
    # Ensure build tools
    python -m pip install build twine --quiet
    
    # Update version in pyproject.toml
    $PyprojectPath = Join-Path $Root "pyproject.toml"
    $Content = Get-Content $PyprojectPath -Raw
    $Content = $Content -replace 'version = "[^"]*"', "version = `"$Version`""
    Set-Content -Path $PyprojectPath -Value $Content -NoNewline
    
    # Build wheel
    python -m build --wheel --outdir $DistDir
    
    # Copy to artifacts
    Get-ChildItem -Path $DistDir -Filter "*.whl" | Copy-Item -Destination $ArtifactDir
    
    Write-Host "✓ Wheel built" -ForegroundColor Green
} finally {
    Pop-Location
}

# ============================================================================
# Step 2: Windows Executable (PyInstaller)
# ============================================================================
if (-not $SkipExe) {
    Write-Host "`n[2/4] Building Windows executable..." -ForegroundColor Yellow
    
    Push-Location $Root
    try {
        # Ensure PyInstaller and deps
        python -m pip install pyinstaller msal_extensions --quiet
        pip install -e ".[windows]" --quiet
        
        # Clean previous builds
        if (Test-Path (Join-Path $Root "build")) {
            Remove-Item -Recurse -Force (Join-Path $Root "build")
        }
        
        # Build executable
        pyinstaller work-context-sync.spec --clean --noconfirm
        
        # Verify executable was created
        $ExePath = Join-Path $DistDir "work-context-sync.exe"
        if (-not (Test-Path $ExePath)) {
            throw "Executable not found at $ExePath"
        }
        
        # Copy to artifacts
        Copy-Item -Path $ExePath -Destination $ArtifactDir
        
        # Create ZIP distribution
        $ZipPath = Join-Path $ArtifactDir "work-context-sync-windows.zip"
        $ReadmePath = Join-Path $Root "README.md"
        $ConfigExample = Join-Path $Root "config.example.json"
        
        Compress-Archive -Path $ExePath, $ReadmePath, $ConfigExample -DestinationPath $ZipPath -Force
        
        Write-Host "✓ Executable and ZIP built" -ForegroundColor Green
    } finally {
        Pop-Location
    }
} else {
    Write-Host "`n[2/4] Skipping executable build (-SkipExe)" -ForegroundColor Gray
}

# ============================================================================
# Step 3: MSI Installer (WiX)
# ============================================================================
if (-not $SkipMsi -and -not $SkipExe) {
    Write-Host "`n[3/4] Building MSI installer..." -ForegroundColor Yellow
    
    # Check for WiX
    $wix = Get-Command wix -ErrorAction SilentlyContinue
    if (-not $wix) {
        Write-Warning "WiX not found. Installing..."
        dotnet tool install --global wix --version 4.0.4
        wix extension add -g WixToolset.UI.wixext
    }
    
    Push-Location (Join-Path $Root "installer\wix")
    try {
        # Update version in .wxs
        $WxsPath = Join-Path $Root "installer\wix\work-context-sync.wxs"
        $Content = Get-Content $WxsPath -Raw
        $Content = $Content -replace 'Version="[^"]*"', "Version=`"$Version`""
        Set-Content -Path $WxsPath -Value $Content -NoNewline
        
        # Build MSI
        $MsiPath = Join-Path $DistDir "work-context-sync.msi"
        wix build -o $MsiPath work-context-sync.wxs
        
        if (-not (Test-Path $MsiPath)) {
            throw "MSI not found at $MsiPath"
        }
        
        # Copy to artifacts
        Copy-Item -Path $MsiPath -Destination $ArtifactDir
        
        Write-Host "✓ MSI built" -ForegroundColor Green
    } finally {
        Pop-Location
    }
} else {
    Write-Host "`n[3/4] Skipping MSI build" -ForegroundColor Gray
}

# ============================================================================
# Step 4: Manifest (Winget)
# ============================================================================
Write-Host "`n[4/4] Generating Winget manifest..." -ForegroundColor Yellow

$WingetDir = Join-Path $ArtifactDir "winget"
New-Item -ItemType Directory -Path $WingetDir -Force | Out-Null

# Generate installer manifest
$InstallerYaml = @"
PackageIdentifier: MidtownTechnologyGroup.WorkContextSync
PackageVersion: $Version
MinimumOSVersion: 10.0.0.0
InstallerType: msi
Scope: machine
UpgradeBehavior: install
Installers:
  - Architecture: x64
    InstallerUrl: https://github.com/midtowntg/work-context-sync/releases/download/v$Version/work-context-sync.msi
    InstallerSha256: # Will be filled by winget-create
ManifestType: installer
ManifestVersion: 1.5.0
"@

$InstallerYaml | Set-Content -Path (Join-Path $WingetDir "installer.yaml")

# Generate default locale manifest
$LocaleYaml = @"
PackageIdentifier: MidtownTechnologyGroup.WorkContextSync
PackageVersion: $Version
PackageLocale: en-US
Publisher: Midtown Technology Group
PublisherUrl: https://midtowntg.com
PackageName: Work Context Sync
PackageUrl: https://github.com/midtowntg/work-context-sync
License: MIT
LicenseUrl: https://github.com/midtowntg/work-context-sync/blob/main/LICENSE
ShortDescription: Sync Microsoft 365 work context to LogSeq knowledge graph
Description: |
  Work Context Sync fetches your daily work data from Microsoft 365
  (calendar, email, tasks, Teams) and writes it to your LogSeq knowledge
  graph for GTD-style morning reviews.
Moniker: wcsync
Tags:
  - microsoft365
  - graph-api
  - logseq
  - gtd
  - productivity
  - notes
ManifestType: defaultLocale
ManifestVersion: 1.5.0
"@

$LocaleYaml | Set-Content -Path (Join-Path $WingetDir "locale.yaml")

# Generate version manifest
$VersionYaml = @"
PackageIdentifier: MidtownTechnologyGroup.WorkContextSync
PackageVersion: $Version
DefaultLocale: en-US
ManifestType: version
ManifestVersion: 1.5.0
"@

$VersionYaml | Set-Content -Path (Join-Path $WingetDir "version.yaml")

Write-Host "✓ Winget manifests generated" -ForegroundColor Green

# ============================================================================
# Summary
# ============================================================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Build Complete: v$Version" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Get-ChildItem -Path $ArtifactDir | ForEach-Object {
    $Size = [math]::Round($_.Length / 1KB, 2)
    Write-Host "  $($_.Name) ($Size KB)" -ForegroundColor White
}

Write-Host "`nNext steps:" -ForegroundColor Yellow
Write-Host "  1. Test the MSI: .\dist\work-context-sync.msi" -ForegroundColor Gray
Write-Host "  2. Create GitHub release with artifacts" -ForegroundColor Gray
Write-Host "  3. Submit Winget manifest to microsoft/winget-pkgs" -ForegroundColor Gray
Write-Host "`nRelease checklist: .github\workflows\release.yml" -ForegroundColor Gray
