# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import subprocess


def _write_git_hash():
    root = Path.cwd().resolve()
    hash_path = root / "git_hash.txt"
    git_hash = ""
    try:
        git_hash = subprocess.check_output(
            ["git", "rev-parse", "--short=6", "HEAD"],
            cwd=str(root),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        pass

    if git_hash:
        hash_path.write_text(git_hash, encoding="utf-8")


_write_git_hash()


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('gifs', 'gifs'), ('sound', 'sound'), ('fonts', 'fonts'), ('version.txt', '.'), ('git_hash.txt', '.')],
    hiddenimports=[
        'PIL._tkinter',
        'ameath',
        'ameath.constants',
        'ameath.config',
        'ameath.utils',
        'ameath.pet',
        'ameath.tray',
        'ameath.fonts',
        'ameath.voice',
        'ameath.music_player',
        'ameath.settings',
        'ameath.settings.base',
        'ameath.settings.personalization',
        'ameath.settings.update',
        'ameath.settings.about',
        'ameath.settings.music',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'asyncio', 'test'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ameath',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='gifs\\ameath.ico',
)
