"""Project validation and straight-cut FFmpeg rendering. No UI dependencies."""
from __future__ import annotations

import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import uuid

from .settings import data_directory


class MakerError(ValueError):
    """An actionable editing or media error."""


def ffmpeg_exe():
    configured = os.environ.get('CLASSIC_MAKER_FFMPEG')
    if configured:
        return configured
    executable = shutil.which('ffmpeg')
    if executable:
        return executable
    cached = data_directory() / 'tools' / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
    if cached.is_file():
        return str(cached)
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise MakerError('FFmpeg is missing. Install FFmpeg and add it to PATH, or from the source folder run: python -m pip install ".[bundled]"') from None


def process_options():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


def probe(path):
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise MakerError(f'Media file not found: {source}')
    try:
        result = subprocess.run([ffmpeg_exe(), '-hide_banner', '-protocol_whitelist', 'file,pipe', '-i', str(source)], capture_output=True,
                                encoding='utf-8', errors='replace', timeout=30, **process_options())
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MakerError(f'Cannot read media: {exc}') from exc
    text = result.stderr
    duration = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', text)
    video = re.search(r'Stream[^\n]*Video:[^\n]*', text)
    if not duration or not video:
        raise MakerError(f'{source.name} is not a readable video with a known duration.')
    seconds = int(duration[1]) * 3600 + int(duration[2]) * 60 + float(duration[3])
    if seconds <= 0:
        raise MakerError('This video has no usable duration.')
    return {'id': uuid.uuid4().hex, 'path': str(source), 'name': source.name,
            'start': 0.0, 'end': seconds, 'muted': False,
            'duration': seconds, 'hasAudio': bool(re.search(r'Stream[^\n]*Audio:', text))}


def validate_project(project, base=None):
    if not isinstance(project, dict) or project.get('version') != 1:
        raise MakerError('Open a Classic Maker version 1 JSON project.')
    clips = project.get('clips')
    if not isinstance(clips, list) or len(clips) > 1000:
        raise MakerError('A project must contain a clips array (maximum 1,000 clips).')
    output = project.get('output', {})
    if not isinstance(output, dict) or output.get('resolution', '720p') not in ('720p', '1080p') or output.get('fps', 30) != 30:
        raise MakerError('Choose 720p or 1080p at 30 frames per second.')
    normalized = []
    ids = set()
    cache = {}
    for item in clips:
        if not isinstance(item, dict) or not isinstance(item.get('path'), str) or not item['path']:
            raise MakerError('Each clip needs a local media path.')
        path = Path(item['path']).expanduser()
        if not path.is_absolute():
            path = Path(base or Path.cwd()) / path
        path = str(path.resolve())
        if path not in cache:
            cache[path] = probe(path)
        info = cache[path]
        start, end = item.get('start', 0), item.get('end', info['duration'])
        if any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in (start, end)):
            raise MakerError('Trim times must be finite numbers in seconds.')
        if start < 0 or end <= start or end > info['duration'] + 0.025:
            raise MakerError(f'Invalid trim for {info["name"]}: use 0 ≤ start < end ≤ {info["duration"]:.2f}.')
        if not isinstance(item.get('muted', False), bool):
            raise MakerError('muted must be true or false.')
        clip_id = item.get('id')
        if not isinstance(clip_id, str) or not clip_id or clip_id in ids:
            clip_id = uuid.uuid4().hex
        ids.add(clip_id)
        normalized.append({**info, 'id': clip_id, 'name': str(item.get('name', info['name']))[:200],
                           'start': float(start), 'end': min(float(end), info['duration']), 'muted': item.get('muted', False)})
    return {'version': 1, 'name': str(project.get('name', 'My movie'))[:200], 'clips': normalized,
            'output': {'resolution': output.get('resolution', '720p'), 'fps': 30}}


def _run(command, cancel, on_time):
    # Stderr goes to disk: long jobs cannot fill a pipe or consume unbounded RAM.
    with tempfile.TemporaryFile() as errors:
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors, text=True,
                                       encoding='utf-8', errors='replace', **process_options())
        except OSError as exc:
            raise MakerError(f'Cannot start FFmpeg: {exc}') from exc
        def stop_on_cancel():
            while process.poll() is None:
                if cancel.wait(0.1):
                    try:
                        process.terminate()
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    except OSError:
                        pass
                    return
        watcher = threading.Thread(target=stop_on_cancel, daemon=True)
        watcher.start()
        frames = 0
        try:
            for line in process.stdout:
                if line.startswith('out_time_us='):
                    try:
                        on_time(int(line.split('=', 1)[1]) / 1_000_000)
                    except ValueError:
                        pass
                elif line.startswith('frame='):
                    frames = int(line.split('=', 1)[1])
            process.wait()
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.kill()
                process.wait()
            watcher.join(timeout=4)
        if cancel.is_set():
            raise MakerError('Export cancelled. Your source clips are unchanged.')
        if process.returncode:
            errors.seek(0, 2)
            errors.seek(max(0, errors.tell() - 4000))
            detail = errors.read().decode('utf-8', 'replace').strip()
            raise MakerError(f'FFmpeg could not export the movie. {detail}')
        return frames


def render(project, destination, *, overwrite=False, progress=None, cancel=None, base=None):
    project = validate_project(project, base)
    if not project['clips']:
        raise MakerError('Import at least one clip before exporting.')
    output = Path(destination).expanduser().resolve()
    if output.suffix.lower() != '.mp4':
        raise MakerError('The output filename must end in .mp4.')
    if any(output == Path(clip['path']) for clip in project['clips']):
        raise MakerError('Choose a different output file. Source clips are never overwritten.')
    if output.exists() and not overwrite:
        raise MakerError('Output already exists. Choose a new name or use --overwrite.')
    if not output.parent.is_dir():
        raise MakerError(f'Output folder does not exist: {output.parent}')
    cancel = cancel or threading.Event()
    progress = progress or (lambda value: None)
    duration = sum(c['end'] - c['start'] for c in project['clips'])
    width, height = (1280, 720) if project['output']['resolution'] == '720p' else (1920, 1080)
    ffmpeg = ffmpeg_exe()
    common = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-progress', 'pipe:1']
    with tempfile.TemporaryDirectory(prefix='classic-maker-', dir=output.parent) as work:
        work = Path(work)
        completed = 0.0
        for index, clip in enumerate(project['clips']):
            if cancel.is_set():
                raise MakerError('Export cancelled.')
            length = clip['end'] - clip['start']
            command = common + ['-ss', str(clip['start']), '-protocol_whitelist', 'file,pipe', '-i', clip['path']]
            silent = clip['muted'] or not clip['hasAudio']
            if silent:
                command += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
            command += ['-map', '0:v:0', '-map', '1:a:0' if silent else '0:a:0', '-t', str(length),
                        '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30',
                        '-af', 'aresample=48000:async=1:first_pts=0,apad',
                        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', '-video_track_timescale', '90000',
                        str(work / f'clip-{index:04d}.mp4')]
            frames = _run(command, cancel, lambda t: progress(min(94, (completed + min(t, length)) / duration * 94)))
            if frames < 1:
                raise MakerError(f'The trim for {clip["name"]} contains no video frames. Choose a longer trim.')
            completed += length
        listing = work / 'clips.txt'
        listing.write_text(''.join(f"file 'clip-{i:04d}.mp4'\n" for i in range(len(project['clips']))), encoding='utf-8')
        final = work / 'movie.mp4'
        # AAC packet tails can make concat timestamps uneven. Enforce CFR at the join.
        _run(common + ['-f', 'concat', '-safe', '1', '-i', str(listing),
                       '-vf', 'fps=30', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
                       '-pix_fmt', 'yuv420p', '-c:a', 'copy', '-video_track_timescale', '90000',
                       '-movflags', '+faststart', str(final)], cancel,
             lambda t: progress(min(99, 94 + t / duration * 5)))
        if cancel.is_set():
            raise MakerError('Export cancelled.')
        # A concurrent output creation must not be silently clobbered.
        if overwrite:
            os.replace(final, output)
        else:
            try:
                os.link(final, output)
            except FileExistsError:
                raise MakerError('Output already exists. Choose a new name.') from None
            except OSError:
                with output.open('xb') as target, final.open('rb') as source:
                    shutil.copyfileobj(source, target)
        progress(100)
    return output
