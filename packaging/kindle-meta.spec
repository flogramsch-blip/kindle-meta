# PyInstaller-Spec für die kindle-meta-Desktop-App.
#
# Build:  pip install -e ".[gui,build]"
#         pyinstaller packaging/kindle-meta.spec
#
# Ergebnis: dist/kindle-meta (Ein-Datei-App, kein Python nötig).
#
# Viele Abhängigkeiten werden zur Laufzeit "lazy" importiert (ebooklib, pypdf,
# PIL, requests). PyInstaller findet sie über die statische Analyse nicht
# zuverlässig – daher als hiddenimports aufgeführt.

block_cipher = None

hiddenimports = [
    "ebooklib",
    "ebooklib.epub",
    "pypdf",
    "PIL",
    "PIL.Image",
    "requests",
]

a = Analysis(
    ["kindle_meta_gui.py"],
    pathex=[".."],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
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
    name="kindle-meta",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI-App ohne Konsolenfenster
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
