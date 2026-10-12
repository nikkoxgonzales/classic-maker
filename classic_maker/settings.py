"""Platform-native user data paths shared by the CLI and editor."""
import os
from pathlib import Path
import sys


def data_directory():
    if os.environ.get('CLASSIC_MAKER_DATA'):
        return Path(os.environ['CLASSIC_MAKER_DATA']).expanduser().resolve()
    if os.name == 'nt':
        root = Path(os.environ.get('LOCALAPPDATA', Path.home()))
    elif sys.platform == 'darwin':
        root = Path.home() / 'Library' / 'Application Support'
    else:
        root = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    return root / 'classic-maker'
