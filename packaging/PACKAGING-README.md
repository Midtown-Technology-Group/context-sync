# Packaging & Distribution

This directory contains all packaging configurations for distributing Work Context Sync to your team or the public.

## Distribution Methods

### 1. Python Wheel (pip install)

**Best for**: Python developers, CI/CD pipelines

```bash
pip install mtg-work-context-sync
work-context-sync sync today
```

Build:
```powershell
python -m build --wheel
```

### 2. Windows Executable (PyInstaller)

**Best for**: End users who don't have Python

Single `.exe` file, no installation required:
```powershell
work-context-sync.exe sync today
```

Build:
```powershell
pyinstaller work-context-sync.spec
```

### 3. MSI Installer (WiX)

**Best for**: IT deployment, enterprise rollouts

Standard Windows installer:
- Adds to `Program Files\Work Context Sync`
- Adds to PATH
- Start Menu shortcut
- Clean uninstall

Build:
```powershell
cd installer/wix
wix build -o work-context-sync.msi work-context-sync.wxs
```

### 4. Winget (Windows Package Manager)

**Best for**: Modern Windows users, one-command install

```powershell
winget install MidtownTechnologyGroup.WorkContextSync
```

Submit to community repo:
```powershell
wingetcreate submit --urls https://github.com/midtowntg/work-context-sync/releases/download/v1.0.0/work-context-sync.msi
```

## Build Scripts

### Quick Build (All Artifacts)

```powershell
.\scripts\build-release.ps1 -Version "1.0.0"
```

This creates:
- `dist/artifacts/*.whl` - Python wheel
- `dist/artifacts/work-context-sync.exe` - Standalone executable
- `dist/artifacts/work-context-sync-windows.zip` - Portable ZIP
- `dist/artifacts/work-context-sync.msi` - Windows installer
- `dist/artifacts/winget/` - Winget manifests

### Selective Build

```powershell
# Skip MSI (faster, no WiX needed)
.\scripts\build-release.ps1 -Version "1.0.0" -SkipMsi

# Wheel only (fastest)
python -m build --wheel
```

## Prerequisites

### For Wheel/Exe (Required)
- Python 3.10+
- pip
- build: `pip install build pyinstaller`

### For MSI (Optional)
- WiX 4.0+: `dotnet tool install --global wix`
- WiX UI extension: `wix extension add -g WixToolset.UI.wixext`

### For GitHub Releases (Optional)
- Push to trigger `release.yml` workflow
- Creates all artifacts automatically

## Automated Releases

The `.github/workflows/release.yml` GitHub Actions workflow:

1. Triggers on tag push (`v*`)
2. Builds wheel (Ubuntu)
3. Builds Windows exe (Windows)
4. Builds MSI (Windows)
5. Creates GitHub release with all artifacts
6. Generates release notes

**Usage**:
```bash
git tag v1.0.0
git push origin v1.0.0
```

## Version Management

Update version in:
1. `pyproject.toml` - Python package version
2. `setup.py` - Legacy setuptools version
3. `installer/wix/work-context-sync.wxs` - MSI version
4. `work-context-sync.spec` - PyInstaller version (optional)

Or use build script which updates automatically:
```powershell
.\scripts\build-release.ps1 -Version "1.1.0"
```

## Security Considerations

### Code Signing (Recommended)

For MSI/exe distribution, sign with your org's certificate:

```powershell
# Sign MSI
signtool sign /a /fd SHA256 /tr http://timestamp.digicert.com work-context-sync.msi

# Sign EXE
signtool sign /a /fd SHA256 work-context-sync.exe
```

Update WiX config:
```xml
<Package ...>
  <Property Id="MSISIGN" Value="1" />
  <CertificateRef Id="YourCertId" />
</Package>
```

### Virus Scanning

Upload to VirusTotal before release:
https://www.virustotal.com

## Team Distribution

### Internal Share (Easiest)

```powershell
# Build
.\scripts\build-release.ps1 -Version "1.0.0"

# Copy to share
Copy-Item dist\artifacts\* \\server\tools\work-context-sync\releases\v1.0.0\
```

### GitHub Release (Recommended)

1. Push version tag
2. Workflow builds all artifacts
3. Team downloads from GitHub releases page
4. Or use `winget install` if published

### Private Winget Repository

For internal tools, host private winget repo:
```powershell
winget source add -n mtg-internal -a https://winget.yourcompany.com
winget install --source mtg-internal WorkContextSync
```

## Troubleshooting

### "WiX not found"

```powershell
dotnet tool install --global wix --version 4.0.4
```

### "PyInstaller not found"

```powershell
pip install pyinstaller
```

### "Build fails with missing imports"

Check `work-context-sync.spec` hiddenimports list. Add missing packages:
```python
hiddenimports=['missing_package'],
```

### "MSI fails to install"

- Check Windows version (requires 10/11)
- Run as administrator
- Check Event Viewer for MSI errors

## File Structure

```
packaging/
├── README.md                    # This file
├── pyproject.toml              # Modern Python packaging
├── setup.py                    # Legacy setuptools
├── work-context-sync.spec      # PyInstaller config
├── scripts/
│   └── build-release.ps1       # All-in-one build script
├── installer/
│   └── wix/
│       └── work-context-sync.wxs   # MSI source
└── .github/workflows/
    └── release.yml             # GitHub Actions
```

## References

- [PyInstaller](https://pyinstaller.org/)
- [WiX Toolset](https://wixtoolset.org/)
- [Winget Packaging](https://learn.microsoft.com/windows/package-manager/package/)
- [Python Packaging](https://packaging.python.org/)
