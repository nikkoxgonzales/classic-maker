"""Deterministic request/shutdown transition against a real local server."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from classic_maker import server
from classic_maker.media import ffmpeg_exe, process_options


class ShutdownTests(unittest.TestCase):
    def test_request_in_validation_cannot_start_export_after_shutdown(self):
        with tempfile.TemporaryDirectory(prefix='classic-maker-shutdown-') as temporary:
            root = Path(temporary)
            source = root / 'source.mp4'
            subprocess.run([ffmpeg_exe(), '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                            '-i', 'color=blue:s=160x90:r=30:d=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(source)],
                           check=True, capture_output=True, **process_options())
            project = {'version': 1, 'clips': [{'path': str(source), 'start': 0, 'end': 1, 'muted': False}]}
            validated, proceed = threading.Event(), threading.Event()
            original = server.validate_project
            def held_validation(value):
                result = original(value)
                validated.set()
                if not proceed.wait(10):
                    raise RuntimeError('Test barrier timed out')
                return result
            with patch.dict(os.environ, {'CLASSIC_MAKER_DATA': str(root / 'data')}):
                editor = server.EditorServer(0)
            serving = threading.Thread(target=editor.serve_forever, daemon=True)
            serving.start()
            def request():
                endpoint = f'http://127.0.0.1:{editor.server_port}/api/export'
                payload = Request(endpoint, data=json.dumps(project).encode(),
                                  headers={'Content-Type': 'application/json', 'X-Classic-Maker-Token': editor.token})
                try:
                    with urlopen(payload, timeout=15) as response:
                        return response.status, json.load(response)
                except HTTPError as error:
                    return error.code, json.load(error)
            try:
                with patch.object(server, 'validate_project', held_validation), ThreadPoolExecutor(max_workers=1) as workers:
                    result = workers.submit(request)
                    try:
                        self.assertTrue(validated.wait(10), 'Request never reached media validation')
                        editor.shutdown_jobs()
                    finally:
                        proceed.set()
                    status, body = result.result(timeout=15)
                    self.assertEqual(status, 400)
                    self.assertIn('closing', body['error'])
                    # A rejected late request must not strand the sole export slot.
                    self.assertTrue(editor.export_lock.acquire(blocking=False))
                    editor.export_lock.release()
            finally:
                proceed.set()
                editor.shutdown_jobs()
                editor.shutdown()
                editor.server_close()
                serving.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
