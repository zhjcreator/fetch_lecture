# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.building.api import PYZ, EXE
from PyInstaller.building.build_main import Analysis

current_dir = os.path.abspath('.')

block_cipher = None

a = Analysis(
    ['gui/app.py'],
    pathex=[current_dir],
    binaries=[],
    datas=[
        ('captcha_hash_table.csv', '.'),
        ('seu_auth.py', '.'),
        ('gui/backend.py', 'gui'),
    ],
    hiddenimports=[
        'json',
        'ddddocr',
        'PIL',
        'rich',
        'requests',
        'Crypto',
        'ssl',
        'PyQt6',
        'PyQt6.QtWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='fetch_lecture_gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,   # GUI 模式，不显示控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
