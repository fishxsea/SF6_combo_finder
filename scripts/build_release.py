"""Build and smoke-test a native executable, then zip its complete folder."""
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parent.parent


def main():
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm',
                    str(ROOT / 'sf-combo-finder.spec')], cwd=ROOT, check=True)
    bundle = ROOT / 'dist' / 'sf-combo-finder'
    executable = bundle / ('sf-combo-finder.exe' if sys.platform == 'win32' else 'sf-combo-finder')
    # Run away from the checkout to verify that the bundled roster is sufficient.
    subprocess.run([str(executable), '--cli', '--list-characters'], cwd=bundle,
                   check=True, timeout=60)
    subprocess.run([str(executable), '--check-installation'], cwd=bundle,
                   check=True, timeout=60)
    if sys.platform == 'darwin':
        launcher = bundle / 'Start SF Combo Finder.command'
        launcher.write_text('#!/bin/sh\ncd -- "$(dirname -- "$0")" || exit 1\nexec ./sf-combo-finder "$@"\n')
        launcher.chmod(0o755)
    for name in ['DATA_NOTICE.md', 'DATA_SOURCES.md']:
        shutil.copy2(ROOT / name, bundle / name)
    (bundle / 'START_HERE.txt').write_text(
        'SF6 Combo Finder\n\n'
        'Extract the entire archive before running. Keep the _internal folder.\n'
        'Windows: double-click sf-combo-finder.exe.\n'
        'macOS: double-click Start SF Combo Finder.command.\n'
        'Linux: open a terminal here and run ./sf-combo-finder.\n\n'
        'For CLI output, run sf-combo-finder --cli --help (use .exe on Windows).\n'
        'Favorites and preferences are saved in your user app-data directory.\n'
        'Read DATA_NOTICE.md for the bundled data attribution.\n', encoding='utf-8')
    release_dir = ROOT / 'dist' / 'releases'
    release_dir.mkdir(exist_ok=True)
    archive = release_dir / f'sf-combo-finder-{platform.system().lower()}-{platform.machine().lower()}.zip'
    # ZipFile records executable permissions for Unix extractors.
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
        for path in sorted(bundle.rglob('*')):
            output.write(path, path.relative_to(bundle.parent))
    print(f'Release archive: {archive}')


if __name__ == '__main__':
    main()
