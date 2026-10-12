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
    video = any('Video:' in line and '(attached pic)' not in line
                for line in text.splitlines() if 'Stream' in line)
    audio = bool(re.search(r'Stream[^\n]*Audio:', text))
    if not duration or not (video or audio):
        raise MakerError(f'{source.name} is not readable video or audio with a known duration.')
    seconds = int(duration[1]) * 3600 + int(duration[2]) * 60 + float(duration[3])
    if seconds <= 0:
        raise MakerError('This media has no usable duration.')
    return {'id': uuid.uuid4().hex, 'path': str(source), 'name': source.name,
            'start': 0.0, 'end': seconds, 'muted': False, 'volume': 1.0,
            'duration': seconds, 'hasAudio': audio, 'kind': 'video' if video else 'audio'}


def _number(value, label, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise MakerError(f'{label} must be a finite number.')
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise MakerError(f'{label} is outside its allowed range.')
    return float(value)


def validate_project(project, base=None):
    if not isinstance(project, dict) or type(project.get('version')) is not int or project['version'] not in (1, 2):
        raise MakerError('Open a Classic Maker version 1 or 2 JSON project.')
    # One import migration; all editing, saving, and rendering uses the v2 model.
    if project['version'] == 1:
        project = {**project, 'version': 2, 'tracks': {'video': project.get('clips'), 'audio': [], 'effects': []}}
    tracks = project.get('tracks')
    if not isinstance(tracks, dict):
        raise MakerError('A version 2 project needs video, audio, and effects tracks.')
    limits = {'video': 1000, 'audio': 64, 'effects': 256}
    for lane, maximum in limits.items():
        if not isinstance(tracks.get(lane), list) or len(tracks[lane]) > maximum:
            raise MakerError(f'The {lane} track must be an array (maximum {maximum} items).')
    output = project.get('output', {})
    if not isinstance(output, dict) or output.get('resolution', '720p') not in ('720p', '1080p') or output.get('fps', 30) != 30:
        raise MakerError('Choose 720p or 1080p at 30 frames per second.')
    normalized = {lane: [] for lane in limits}
    ids, cache = set(), {}
    def identifier(item):
        value = item.get('id')
        if not isinstance(value, str) or not value or value in ids:
            value = uuid.uuid4().hex
        ids.add(value)
        return value
    for lane in ('video', 'audio'):
        for item in tracks[lane]:
            if not isinstance(item, dict) or not isinstance(item.get('path'), str) or not item['path']:
                raise MakerError('Each media clip needs a local source path.')
            path = Path(item['path']).expanduser()
            if not path.is_absolute():
                path = Path(base or Path.cwd()) / path
            path = str(path.resolve())
            if path not in cache:
                cache[path] = probe(path)
            info = cache[path]
            if lane == 'video' and info['kind'] != 'video':
                raise MakerError(f'{info["name"]} is audio. Put it on the Audio track.')
            if lane == 'audio' and not info['hasAudio']:
                raise MakerError(f'{info["name"]} has no sound to put on the Audio track.')
            start = _number(item.get('start', 0), 'Trim start', 0)
            end = _number(item.get('end', info['duration']), 'Trim end', 0)
            if end <= start or end > info['duration'] + 0.025:
                raise MakerError(f'Invalid trim for {info["name"]}: use 0 ≤ start < end ≤ {info["duration"]:.2f}.')
            if not isinstance(item.get('muted', False), bool):
                raise MakerError('muted must be true or false.')
            clip = {**info, 'id': identifier(item), 'name': str(item.get('name', info['name']))[:200],
                    'start': start, 'end': min(end, info['duration']), 'muted': item.get('muted', False),
                    'volume': _number(item.get('volume', 1), 'Volume', 0, 1)}
            if lane == 'audio':
                clip['at'] = _number(item.get('at', 0), 'Audio position', 0)
                if isinstance(item.get('videoId'), str) and item['videoId']:
                    clip['videoId'] = item['videoId']
            normalized[lane].append(clip)
    ranges = {'brightness': (-1, 1, 0), 'contrast': (0, 2, 1), 'grayscale': (0, 1, 1), 'sepia': (0, 1, 1)}
    for item in tracks['effects']:
        if not isinstance(item, dict) or item.get('type') not in ranges:
            raise MakerError('Choose a brightness, contrast, grayscale, or sepia effect.')
        kind = item['type']
        low, high, default = ranges[kind]
        length = _number(item.get('duration'), 'Effect duration', 0)
        if length <= 0:
            raise MakerError('Effect duration must be greater than zero.')
        normalized['effects'].append({'id': identifier(item), 'type': kind,
                                      'at': _number(item.get('at', 0), 'Effect position', 0),
                                      'duration': length, 'value': _number(item.get('value', default), 'Effect amount', low, high)})
    return {'version': 2, 'name': str(project.get('name', 'My movie'))[:200], 'tracks': normalized,
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


def _clip_effects(effects, clip_at, length):
    """Movie-time effect windows converted to clip-local time for one -vf chain."""
    parts = []
    for effect in effects:
        start = max(0.0, effect['at'] - clip_at)
        end = min(length, effect['at'] + effect['duration'] - clip_at)
        if start >= end or start >= length:
            continue
        value, kind = effect['value'], effect['type']
        enabled = f":enable='gte(t,{start:.6f})*lt(t,{end:.6f})'"
        if kind == 'brightness':
            parts.append(f'eq=brightness={value:.6f}' + enabled)
        elif kind == 'contrast':
            parts.append(f'eq=contrast={value:.6f}' + enabled)
        else:
            target = ((.2126, .7152, .0722),) * 3 if kind == 'grayscale' else (
                (.393, .769, .189), (.349, .686, .168), (.272, .534, .131))
            channels = ('r', 'g', 'b')
            coefficients = []
            for row in range(3):
                for column in range(3):
                    coefficient = (1 - value if row == column else 0) + value * target[row][column]
                    coefficients.append(f'{channels[row]}{channels[column]}={coefficient:.6f}')
            parts.append('colorchannelmixer=' + ':'.join(coefficients) + enabled)
    return parts


def render(project, destination, *, overwrite=False, progress=None, cancel=None, base=None):
    project = validate_project(project, base)
    video = project['tracks']['video']
    audio = project['tracks']['audio']
    if not video:
        raise MakerError('Import at least one video clip before exporting.')
    output = Path(destination).expanduser().resolve()
    if output.suffix.lower() != '.mp4':
        raise MakerError('The output filename must end in .mp4.')
    if any(output == Path(clip['path']) for clip in video + audio):
        raise MakerError('Choose a different output file. Source clips are never overwritten.')
    if output.exists() and not overwrite:
        raise MakerError('Output already exists. Choose a new name or use --overwrite.')
    if not output.parent.is_dir():
        raise MakerError(f'Output folder does not exist: {output.parent}')
    cancel = cancel or threading.Event()
    progress = progress or (lambda value: None)
    duration = sum(c['end'] - c['start'] for c in video)
    width, height = (1280, 720) if project['output']['resolution'] == '720p' else (1920, 1080)
    ffmpeg = ffmpeg_exe()
    common = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-progress', 'pipe:1']
    with tempfile.TemporaryDirectory(prefix='classic-maker-', dir=output.parent) as directory:
        work = Path(directory)
        completed = 0.0
        for index, clip in enumerate(video):
            if cancel.is_set():
                raise MakerError('Export cancelled.')
            length = clip['end'] - clip['start']
            filters = f'scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30:eof_action=pass'
            effects = _clip_effects(project['tracks']['effects'], completed, length)
            if effects:
                filters += ',' + ','.join(effects)
            if len(filters) > 24000:
                raise MakerError(f'Too many effects overlap "{clip["name"]}". Remove some effects or spread them across the movie.')
            command = common + ['-ss', str(clip['start']), '-protocol_whitelist', 'file,pipe', '-i', clip['path']]
            silent = clip['muted'] or not clip['hasAudio'] or clip['volume'] == 0
            if silent:
                command += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
            command += ['-map', '0:v:0', '-map', '1:a:0' if silent else '0:a:0', '-t', str(length),
                        '-vf', filters,
                        '-af', f'aresample=48000:async=1:first_pts=0,volume={clip["volume"]:.9f},apad',
                        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
                        '-c:a', 'pcm_s16le', '-ar', '48000', '-ac', '2', '-f', 'nut',
                        str(work / f'clip-{index:04d}.nut')]
            frames = _run(command, cancel, lambda t: progress(min(75, (completed + min(t, length)) / duration * 75)))
            if frames < 1:
                raise MakerError(f'The trim for {clip["name"]} contains no video frames. Choose a longer trim.')
            completed += length
        listing = work / 'clips.txt'
        # PCM intermediates have no AAC packet tail; declared lengths anchor cuts to movie time.
        listing.write_text(''.join(f"file 'clip-{i:04d}.nut'\nduration {clip['end'] - clip['start']:.9f}\n"
                                   for i, clip in enumerate(video)), encoding='utf-8')
        active_audio = [clip for clip in audio if clip['at'] < duration and not clip['muted'] and clip['volume'] > 0]
        for index, clip in enumerate(active_audio):
            length = min(clip['end'] - clip['start'], duration - clip['at'])
            command = common + ['-ss', str(clip['start']), '-protocol_whitelist', 'file,pipe', '-i', clip['path'],
                                '-map', '0:a:0', '-vn', '-t', str(length),
                                '-af', f'aresample=48000:async=1:first_pts=0,volume={clip["volume"]:.9f},apad',
                                '-c:a', 'pcm_s16le', '-ar', '48000', '-ac', '2', str(work / f'audio-{index:04d}.wav')]
            _run(command, cancel, lambda t: progress(min(85, 75 + (index + min(t / length, 1)) / len(active_audio) * 10)))
        command = common + ['-f', 'concat', '-safe', '1', '-i', str(listing)]
        # Effects live in per-clip -vf chains; the final graph only mixes audio, so it
        # stays small enough to pass inline on FFmpeg builds without -filter_complex_script.
        graph = ['[0:v]fps=30[v]',
                 f'[0:a]aresample=48000:async=1:first_pts=0,apad,atrim=duration={duration:.9f},asetpts=PTS-STARTPTS[base]']
        labels = ['[base]']
        for index, clip in enumerate(active_audio):
            command += ['-i', str(work / f'audio-{index:04d}.wav')]
            label = f'a{index}'
            delay = f',adelay={round(clip["at"] * 1000)}:all=1' if clip['at'] > 0 else ''
            graph.append(f'[{index + 1}:a]asetpts=PTS-STARTPTS{delay},apad,atrim=duration={duration:.9f}[{label}]')
            labels.append(f'[{label}]')
        if active_audio:
            graph.append(''.join(labels) + f'amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0,alimiter=limit=0.95:level=0:latency=1[a]')
        else:
            graph.append('[base]anull[a]')
        final = work / 'movie.mp4'
        _run(command + ['-filter_complex', ';'.join(graph), '-map', '[v]', '-map', '[a]',
                        '-t', str(duration), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
                        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
                        '-video_track_timescale', '90000', '-movflags', '+faststart', str(final)], cancel,
             lambda t: progress(min(99, 85 + t / duration * 14)))
        if cancel.is_set():
            raise MakerError('Export cancelled.')
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
