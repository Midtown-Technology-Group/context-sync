# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for work-context-sync standalone executable.

Build command:
    pyinstaller work-context-sync.spec

Output:
    dist/work-context-sync.exe - Standalone executable (no Python required)
"""

from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT
from PyInstaller.building.api import BUNDLE
import os

block_cipher = None

# Analysis - what to include
a = Analysis(
    ['src/work_context_sync/app.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        # Include any data files
        ('config.example.json', '.'),
    ],
    hiddenimports=[
        # MSAL and dependencies that might not be auto-detected
        'msal',
        'msal_extensions',
        'pydantic',
        'pydantic_core',
        'requests',
        'cryptography',
        'jwt',
        'urllib3',
        'charset_normalizer',
        'certifi',
        'idna',
        # Win32 crypto for DPAPI
        'win32crypt',
        'win32cred',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude test frameworks to reduce size
        'pytest',
        'unittest',
        ' doctest',
        # Exclude unused crypto
        'cryptography.hazmat.primitives.ciphers.aead',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Console executable (shows output)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='work-context-sync',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep console for output
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Could add: icon='assets/icon.ico'
    version='version.txt',  # Optional: version resource
)

# Optional: Create a Windows Installer with Inno Setup or WiX
# See: build-installer.ps1 for WiX approach
