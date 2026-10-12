"""Optional, explicit first-run download. FFmpeg is not redistributed in app releases."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import ssl
import tempfile
import zipfile
from urllib.request import urlopen

from .media import MakerError


def download_context():
    context = ssl.create_default_context()
    # macOS portable Python may have no system CA store. Keep full verification.
    context.load_verify_locations(cafile=str(Path(__file__).with_name('cacert.pem')))
    return context


def install_ffmpeg(directory):
    machine = platform.machine().lower()
    system = platform.system()
    if system == 'Windows' and machine in ('amd64', 'x86_64'):
        tag = 'win_amd64'
    elif system == 'Darwin' and machine in ('arm64', 'aarch64'):
        tag = 'macosx_11_0_arm64'
    elif system == 'Darwin' and machine in ('amd64', 'x86_64'):
        tag = 'macosx_10_9_intel.macosx_10_9_x86_64'
    elif system == 'Linux' and machine in ('amd64', 'x86_64'):
        tag = 'manylinux2014_x86_64'
    elif system == 'Linux' and machine in ('arm64', 'aarch64'):
        tag = 'manylinux2014_aarch64'
    else:
        raise MakerError('Automatic FFmpeg setup is unavailable on this platform. Install FFmpeg with your system package manager.')
    # Pinned publisher release, HTTPS, and verified wheel digest before extraction.
    context = download_context()
    with urlopen('https://pypi.org/pypi/imageio-ffmpeg/0.6.0/json', timeout=30, context=context) as response:
        metadata = json.load(response)
    wheel = next((item for item in metadata['urls'] if item['filename'].endswith(f'-{tag}.whl')), None)
    if not wheel or not wheel['url'].startswith('https://files.pythonhosted.org/'):
        raise MakerError('A trusted FFmpeg download is not available for this platform.')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / ('ffmpeg.exe' if system == 'Windows' else 'ffmpeg')
    with tempfile.TemporaryDirectory(prefix='setup-', dir=directory) as working:
        archive = Path(working) / 'ffmpeg.whl'
        digest = hashlib.sha256()
        size = 0
        with urlopen(wheel['url'], timeout=60, context=context) as response, archive.open('wb') as target:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > wheel['size']:
                    raise MakerError('FFmpeg download size did not match the publisher metadata.')
                digest.update(chunk)
                target.write(chunk)
        if size != wheel['size'] or digest.hexdigest() != wheel['digests']['sha256']:
            raise MakerError('FFmpeg download verification failed. Try again on a trusted connection.')
        with zipfile.ZipFile(archive) as package:
            binaries = [name for name in package.namelist() if name.startswith('imageio_ffmpeg/binaries/ffmpeg-') and not name.endswith('/')]
            if len(binaries) != 1:
                raise MakerError('The downloaded package does not contain the expected FFmpeg executable.')
            executable = Path(working) / destination.name
            with package.open(binaries[0]) as source, executable.open('wb') as target:
                shutil.copyfileobj(source, target)
            executable.chmod(0o755)
            os.replace(executable, destination)
    return destination
