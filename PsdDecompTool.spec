# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all


# tkinterdnd2는 파이썬 모듈 외에 tkdnd 플랫폼별 런타임 파일이 필요하므로 한 번에 수집합니다.
tkinterdnd2_datas, tkinterdnd2_binaries, tkinterdnd2_hiddenimports = collect_all('tkinterdnd2')
app_datas = [
    ('assets\\app.ico', 'assets'),
]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=tkinterdnd2_binaries,
    datas=tkinterdnd2_datas + app_datas,
    hiddenimports=tkinterdnd2_hiddenimports + ['tkinterdnd2', 'tkinterdnd2.TkinterDnD'],
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
    [],
    exclude_binaries=True,
    name='PsdDecompTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\app.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PsdDecompTool',
)
