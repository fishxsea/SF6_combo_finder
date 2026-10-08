from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH)
datas, binaries, hiddenimports = collect_all('textual')
datas += [
    (str(root / 'sf_combo_finder' / 'characters.json'), 'sf_combo_finder'),
    (str(root / 'DATA_NOTICE.md'), 'sf_combo_finder'),
]
a = Analysis(
    [str(root / 'scripts' / 'frozen_launcher.py')],
    pathex=[str(root)], binaries=binaries, datas=datas,
    hiddenimports=hiddenimports,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name='sf-combo-finder', console=True,
)
coll = COLLECT(exe, a.binaries, a.datas, name='sf-combo-finder')
