# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['ddddocr_api.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('model.onnx', '.'),
        ('charsets.json', '.'),
        ('captcha_hash_table.csv', '.')
    ],
    hiddenimports=[
        'ddddocr',
        'ddddocr.recognizer',
        'ddddocr.detector',
        'ddddocr.utils',
        'flask',
        'threading',
        'base64',
        'json',
        'io',
        'os'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    exclude_binaries=False,  # 设置为False以包含所有依赖
    name='ddddocr_api',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
