"""Human UI launcher and JSON-friendly command line entry point."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from . import __version__
from .media import MakerError, ffmpeg_exe, probe, process_options, render
from .server import serve


def main():
    parser = argparse.ArgumentParser(prog='classic-maker', description='Simple, local FFmpeg video editor. No command opens the editor.')
    parser.add_argument('--version', action='version', version=__version__)
    commands = parser.add_subparsers(dest='command')
    ui = commands.add_parser('serve', help='Open the local video editor')
    ui.add_argument('--port', type=int, default=0, help='Local port (0 chooses a free port)')
    ui.add_argument('--no-browser', action='store_true')
    inspect = commands.add_parser('probe', help='Print a video clip as JSON')
    inspect.add_argument('path')
    export = commands.add_parser('render', help='Export a JSON project as MP4')
    export.add_argument('project')
    export.add_argument('-o', '--output', required=True)
    export.add_argument('--overwrite', action='store_true')
    commands.add_parser('doctor', help='Check FFmpeg availability')
    args = parser.parse_args()
    try:
        if args.command == 'probe':
            print(json.dumps(probe(args.path), ensure_ascii=False, indent=2))
        elif args.command == 'render':
            source = Path(args.project).resolve()
            project = json.loads(source.read_text(encoding='utf-8-sig'))
            output = render(project, args.output, overwrite=args.overwrite, base=source.parent,
                            progress=lambda p: print(f'Export: {p:.0f}%', file=sys.stderr, flush=True))
            print(json.dumps({'output': str(output)}, ensure_ascii=False))
        elif args.command == 'doctor':
            executable = ffmpeg_exe()
            result = subprocess.run([executable, '-version'], capture_output=True, text=True, timeout=10, **process_options())
            if result.returncode:
                raise MakerError('FFmpeg cannot run. Reinstall FFmpeg or the bundled dependency.')
            print(json.dumps({'ok': True, 'ffmpeg': executable, 'version': result.stdout.splitlines()[0]}))
        else:
            serve(getattr(args, 'port', 0), not getattr(args, 'no_browser', False))
    except (MakerError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f'Classic Maker: {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Export interrupted. Source files are unchanged.', file=sys.stderr)
        return 130
    return 0


if __name__ == '__main__':
    sys.exit(main())
