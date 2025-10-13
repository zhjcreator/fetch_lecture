# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.building.api import PYZ, EXE, COLLECT
from PyInstaller.building.build_main import Analysis
from PyInstaller.utils.hooks import collect_data_files

# 获取当前目录
current_dir = os.path.abspath('.')

# 分析主程序
block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[current_dir],
    binaries=[],
    datas=[
        ('model.onnx', '.'),
        ('charsets.json', '.'),
        ('captcha_hash_table.csv', '.'),
        ('seu_auth.py', '.')
    ],
    hiddenimports=[
        'json',
        'ddddocr',
        'PIL',
        'rich',
        'requests',
        'Crypto',
        'ssl'
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

# 创建exe文件
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='fetch_lecture',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 保持控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# 如果需要创建单一文件夹，可以使用COLLECT
# coll = COLLECT(
#     exe,
#     a.binaries,
#     a.zipfiles,
#     a.datas,
#     strip=False,
#     upx=True,
#     upx_exclude=[],
#     name='fetch_lecture',
# )