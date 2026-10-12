"""Loopback-only local editor. No cloud services or uploaded remote media."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import hashlib
import mimetypes
from pathlib import Path
import secrets
import threading
import subprocess
from urllib.parse import parse_qs, urlsplit
import uuid
import webbrowser

from . import __version__
from .media import MakerError, ffmpeg_exe, probe, process_options, render, validate_project
from .settings import data_directory
from .setup import install_ffmpeg




class EditorServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, port):
        super().__init__(('127.0.0.1', port), Handler)
        self.token = secrets.token_urlsafe(32)
        self.data = data_directory()
        (self.data / 'media').mkdir(parents=True, exist_ok=True)
        (self.data / 'exports').mkdir(exist_ok=True)
        (self.data / 'thumbnails').mkdir(exist_ok=True)
        self.allowed = set()
        self.jobs = {}
        self.lock = threading.Lock()
        self.stopping = False
        self.export_lock = threading.Lock()
        self.setup_lock = threading.Lock()
        self.thumbnail_lock = threading.Lock()
        self.web = Path(__file__).parent / 'web'

    def shutdown_jobs(self):
        with self.lock:
            self.stopping = True
            for job in self.jobs.values():
                job['cancel'].set()


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, format, *args):
        pass  # File paths and session credentials do not belong in request logs.

    def headers_for(self, status, kind, size=None):
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; media-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        if size is not None:
            self.send_header('Content-Length', str(size))

    def respond(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.headers_for(status, 'application/json; charset=utf-8', len(body))
        self.end_headers()
        self.wfile.write(body)

    def boundary(self, mutation=False):
        port = self.server.server_port
        hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        if self.headers.get('Host', '') not in hosts:
            raise MakerError('Only local editor requests are accepted.')
        origin = self.headers.get('Origin')
        if origin and origin not in {f'http://{host}' for host in hosts}:
            raise MakerError('Requests from other websites are not allowed.')
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise MakerError('Requests from other websites are not allowed.')
        if mutation and not secrets.compare_digest(self.headers.get('X-Classic-Maker-Token', ''), self.server.token):
            raise MakerError('Editor session expired. Reload the page and try again.')

    def json_body(self):
        size = self.body_size()
        if size > 4 * 1024 * 1024:
            raise MakerError('Project is too large (maximum 4 MB).')
        try:
            return json.loads(self.rfile.read(size))
        except (ValueError, UnicodeError):
            raise MakerError('Expected a valid JSON project or request.') from None

    def body_size(self):
        try:
            size = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            size = -1
        if size < 0:
            raise MakerError('Content-Length is required.')
        return size

    def file(self, path, attachment=False):
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        requested = self.headers.get('Range')
        if requested:
            import re
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
            if not match or not any(match.groups()):
                self.headers_for(416, 'text/plain', 0)
                self.send_header('Content-Range', f'bytes */{size}')
                self.end_headers()
                return
            a, b = match.groups()
            if a:
                start, end = int(a), min(int(b), size - 1) if b else size - 1
            else:
                start = max(0, size - int(b))
            if start >= size or end < start:
                self.headers_for(416, 'text/plain', 0)
                self.send_header('Content-Range', f'bytes */{size}')
                self.end_headers()
                return
            status = 206
        self.headers_for(status, mimetypes.guess_type(path.name)[0] or 'application/octet-stream', end - start + 1)
        self.send_header('Accept-Ranges', 'bytes')
        if status == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        if attachment:
            self.send_header('Content-Disposition', 'attachment; filename="classic-maker-movie.mp4"')
        self.end_headers()
        with path.open('rb') as source:
            source.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = source.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_GET(self):
        try:
            self.boundary()
            parsed = urlsplit(self.path)
            route = parsed.path
            if route == '/api/config':
                try:
                    ffmpeg_exe()
                    available = True
                except MakerError:
                    available = False
                self.respond({'token': self.server.token, 'version': __version__, 'ffmpegAvailable': available, 'dataDir': str(self.server.data)})
            elif route in ('/', '/app.js', '/style.css', '/logo.svg'):
                self.file(self.server.web / ('index.html' if route == '/' else route[1:]))
            elif route == '/api/media':
                path = Path(parse_qs(parsed.query).get('path', [''])[0]).resolve()
                if str(path) not in self.server.allowed or not path.is_file():
                    raise MakerError('Import this clip or open its project before previewing it.')
                self.file(path)
            elif route == '/api/thumbnail':
                path = Path(parse_qs(parsed.query).get('path', [''])[0]).resolve()
                if str(path) not in self.server.allowed or not path.is_file():
                    raise MakerError('Import this clip or open its project before previewing it.')
                stat = path.stat()
                key = hashlib.sha256(f'{path}:{stat.st_size}:{stat.st_mtime_ns}'.encode()).hexdigest()
                image = self.server.data / 'thumbnails' / f'{key}.png'
                with self.server.thumbnail_lock:
                    if not image.is_file():
                        temporary = image.with_name(f'{key}-{uuid.uuid4().hex}.png')
                        try:
                            result = subprocess.run(
                                [ffmpeg_exe(), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                                 '-protocol_whitelist', 'file,pipe', '-i', str(path), '-an', '-frames:v', '1',
                                 '-vf', 'scale=160:90:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=160:90:(ow-iw)/2:(oh-ih)/2',
                                 '-update', '1', str(temporary)], capture_output=True, timeout=20, **process_options())
                            if result.returncode or not temporary.is_file():
                                raise MakerError('A thumbnail is not available for this media.')
                            temporary.replace(image)
                        finally:
                            temporary.unlink(missing_ok=True)
                self.file(image)
            elif route.startswith('/api/jobs/') or route.startswith('/api/download/'):
                identifier = route.rsplit('/', 1)[-1]
                with self.server.lock:
                    job = self.server.jobs.get(identifier)
                    snapshot = {k: v for k, v in job.items() if k not in ('cancel', 'path')} if job else None
                if not job:
                    self.respond({'error': 'Export not found.'}, 404)
                elif route.startswith('/api/download/'):
                    if snapshot['status'] != 'done':
                        raise MakerError('The movie is not ready to download.')
                    self.file(job['path'], attachment=True)
                else:
                    self.respond(snapshot)
            else:
                self.respond({'error': 'Not found.'}, 404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (MakerError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
            self.respond({'error': str(exc)}, 400)

    def do_POST(self):
        try:
            self.boundary(mutation=True)
            parsed = urlsplit(self.path)
            route = parsed.path
            if route == '/api/import':
                size = self.body_size()
                name = parse_qs(parsed.query).get('name', ['clip.mp4'])[0].replace('\\', '/').rsplit('/', 1)[-1]
                suffix = Path(name).suffix[:12]
                if not suffix or not suffix[1:].isalnum():
                    suffix = '.video'
                path = self.server.data / 'media' / (uuid.uuid4().hex + suffix)
                try:
                    with path.open('xb') as target:
                        remaining = size
                        while remaining:
                            chunk = self.rfile.read(min(256 * 1024, remaining))
                            if not chunk:
                                raise MakerError('The import was interrupted. Try again.')
                            target.write(chunk)
                            remaining -= len(chunk)
                    clip = probe(path)
                    clip['name'] = name[:200]
                except Exception:
                    path.unlink(missing_ok=True)
                    raise
                self.server.allowed.add(str(path.resolve()))
                self.respond(clip)
            elif route == '/api/setup':
                self.json_body()
                if not self.server.setup_lock.acquire(blocking=False):
                    raise MakerError('FFmpeg is already being downloaded. Please wait.')
                try:
                    executable = install_ffmpeg(self.server.data / 'tools')
                    self.respond({'ok': True, 'ffmpeg': str(executable)})
                finally:
                    self.server.setup_lock.release()
            elif route == '/api/probe':
                body = self.json_body()
                clip = probe(body.get('path', ''))
                self.server.allowed.add(clip['path'])
                self.respond(clip)
            elif route == '/api/project':
                project = validate_project(self.json_body())
                self.server.allowed.update(c['path'] for lane in ('video', 'audio') for c in project['tracks'][lane])
                self.respond(project)
            elif route == '/api/export':
                project = validate_project(self.json_body())
                if not project['tracks']['video']:
                    raise MakerError('Import at least one clip before exporting.')
                if not self.server.export_lock.acquire(blocking=False):
                    raise MakerError('A movie is already exporting. Wait for it or cancel it first.')
                identifier = uuid.uuid4().hex
                job = {'id': identifier, 'status': 'running', 'progress': 0,
                       'cancel': threading.Event(), 'path': self.server.data / 'exports' / f'{identifier}.mp4'}
                with self.server.lock:
                    if self.server.stopping:
                        self.server.export_lock.release()
                        raise MakerError('Classic Maker is closing. Restart it before exporting.')
                    self.server.jobs[identifier] = job
                def export():
                    def update(value):
                        with self.server.lock:
                            job['progress'] = round(value, 1)
                    try:
                        render(project, job['path'], progress=update, cancel=job['cancel'])
                        with self.server.lock:
                            job.update(status='done', progress=100, download=f'/api/download/{identifier}')
                    except Exception as exc:
                        with self.server.lock:
                            job.update(status='error', error=str(exc))
                    finally:
                        self.server.export_lock.release()
                # Non-daemon worker lets shutdown cancellation finish before Python exits.
                threading.Thread(target=export, daemon=False).start()
                self.respond({'id': identifier}, 202)
            elif route == '/api/cancel':
                identifier = self.json_body().get('id')
                with self.server.lock:
                    job = self.server.jobs.get(identifier)
                    if not job or job['status'] != 'running':
                        raise MakerError('No running export to cancel.')
                    job['cancel'].set()
                self.respond({'ok': True})
            else:
                self.respond({'error': 'Not found.'}, 404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (MakerError, OSError, ValueError, TypeError, AttributeError) as exc:
            # Close after rejected bodies so unread bytes cannot become another request.
            self.close_connection = True
            self.respond({'error': str(exc)}, 400)


def serve(port=0, open_browser=True):
    server = EditorServer(port)
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'Classic Maker: {url}', flush=True)
    print('Keep this window open. Press Ctrl+C to quit.', flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown_jobs()
        server.server_close()
