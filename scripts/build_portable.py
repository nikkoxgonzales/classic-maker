"""Build the small portable launcher. FFmpeg is downloaded separately on first use."""
import importlib.metadata
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from classic_maker import __version__


def main():
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
               '--name', 'classic-maker', '--collect-data', 'classic_maker',
               '--exclude-module', 'imageio_ffmpeg']
    if platform.system() == 'Windows':
        command += ['--icon', str(ROOT / 'assets' / 'classic-maker.ico')]
    command += [str(ROOT / 'launcher.py')]
    subprocess.run(command, cwd=ROOT, check=True)
    directory = ROOT / 'dist' / 'classic-maker'
    for filename in ('LICENSE', 'README.md', 'THIRD_PARTY.md'):
        shutil.copy2(ROOT / filename, directory / filename)
    shutil.copytree(ROOT / 'docs', directory / 'docs', dirs_exist_ok=True)
    shutil.copy2(ROOT / 'classic_maker' / 'web' / 'logo.svg', directory / 'logo.svg')
    notices = directory / 'notices'
    notices.mkdir(exist_ok=True)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.is_file():
        shutil.copy2(python_license, notices / 'PYTHON-LICENSE.txt')
    else:
        from urllib.request import urlopen
        from classic_maker.setup import download_context
        version = '.'.join(map(str, sys.version_info[:3]))
        with urlopen(f'https://raw.githubusercontent.com/python/cpython/v{version}/LICENSE', timeout=30, context=download_context()) as response:
            (notices / 'PYTHON-LICENSE.txt').write_bytes(response.read())
    distribution = importlib.metadata.distribution('pyinstaller')
    for file in distribution.files:
        if str(file).endswith('COPYING.txt'):
            shutil.copy2(distribution.locate_file(file), notices / 'PYINSTALLER-LICENSE.txt')
    shutil.copy2(ROOT / 'classic_maker' / 'cacert.LICENSE', notices / 'CA-BUNDLE-LICENSE.txt')
    system = {'Windows': 'windows', 'Darwin': 'macos', 'Linux': 'linux'}[platform.system()]
    machine = platform.machine().lower()
    architecture = 'arm64' if machine in ('aarch64', 'arm64') else 'x86_64'
    archive = ROOT / 'dist' / f'classic-maker-{__version__}-{system}-{architecture}.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as package:
        for path in sorted(directory.rglob('*')):
            if path.is_file():
                package.write(path, path.relative_to(directory.parent))
    print(archive)


if __name__ == '__main__':
    main()
