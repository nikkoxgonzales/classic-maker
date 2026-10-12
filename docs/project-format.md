# Projects, CLI, and local API

Classic Maker uses readable versioned JSON. Clip array order is movie order. No
hidden database or UI state is needed to render a project.

## Project format v1

```json
{
  "version": 1,
  "name": "A weekend away",
  "clips": [
    {
      "id": "first-clip",
      "path": "videos/arrival.mp4",
      "name": "Arrival",
      "start": 0.5,
      "end": 5.0,
      "muted": false
    },
    {
      "id": "second-clip",
      "path": "videos/walk.mp4",
      "name": "An afternoon walk",
      "start": 2.0,
      "end": 8.0,
      "muted": true
    }
  ],
  "output": {"resolution": "720p", "fps": 30}
}
```

- `version` must be `1`. Maximum 1,000 clips. Empty projects can be saved/opened,
  but cannot be exported.
- `path` is a local file, not a URL. CLI relative paths resolve against the JSON
  file's directory. Browser-created projects use absolute persistent-storage paths;
  the HTTP API resolves relative paths against the server's working directory.
- `start` and `end` are finite seconds. `0 ≤ start < end ≤ source duration`.
  End is exclusive; FFmpeg rounds to video/audio sampling boundaries. Export
  duration can differ slightly due to frame boundaries and AAC packet timing.
- `muted` is a boolean. The original audio is preserved unless muted; missing
  audio becomes silence so differently sourced clips join consistently.
- `id` identifies the clip in the project. Missing or duplicate IDs are regenerated.
- `name` is a display label; the media path determines the source.
- `resolution` is `720p` or `1080p`. `fps` is `30`. Export always uses H.264/AAC
  stereo MP4, 16:9 canvas, black-bar fitting, and square pixels.
- `probe` and HTTP project validation also return derived `duration` and `hasAudio`;
  these are recomputed from the source, never trusted as project instructions.

## CLI

Use `python -m classic_maker`, the installed `classic-maker` command, or the
portable executable. No command launches the browser editor.

```sh
python -m classic_maker --version
python -m classic_maker doctor
python -m classic_maker probe videos/arrival.mp4
python -m classic_maker render movie.classic-maker.json -o finished.mp4
python -m classic_maker render movie.classic-maker.json -o finished.mp4 --overwrite
python -m classic_maker serve --no-browser --port 8765
```

- `probe`: JSON clip plus source duration/audio availability on stdout.
- `render`: on success prints `{"output":"absolute/path/to/finished.mp4"}`.
  Progress goes to stderr. The destination's parent folder must already exist.
- Exit code `0` means success; editing/media errors return `1`; interrupted CLI
  export returns `130`. Errors go to stderr.
- Existing output is refused without `--overwrite`. A source path is never an
  export destination, including with `--overwrite`.
- CLI rendering doesn't copy sources. It uses the paths you give it.
- `serve` binds only to `127.0.0.1`. Default port `0` chooses a free local port;
  `--no-browser` prints the URL without opening the browser.
- FFmpeg lookup: `CLASSIC_MAKER_FFMPEG`, system PATH, cached one-time setup,
  then optional `imageio_ffmpeg`. `CLASSIC_MAKER_DATA` overrides app storage.

Example script building a project from existing media:

```python
import json
from pathlib import Path
import subprocess
import sys

clip = json.loads(subprocess.check_output(
    [sys.executable, "-m", "classic_maker", "probe", "holiday.mp4"], text=True
))
clip["start"] = 1.0
clip["end"] = min(clip["duration"], 6.0)
if clip["end"] <= clip["start"]:
    raise ValueError("The source is too short for this trim")
project = {"version": 1, "name": "Holiday", "clips": [clip],
           "output": {"resolution": "720p", "fps": 30}}
Path("holiday.classic-maker.json").write_text(json.dumps(project, indent=2), encoding="utf-8")
subprocess.run([sys.executable, "-m", "classic_maker", "render",
                "holiday.classic-maker.json", "-o", "holiday-edited.mp4"], check=True)
```

## Local HTTP API

The CLI is the simplest automation interface. For UI integration, get
`/api/config`, then send its session `token` as `X-Classic-Maker-Token` on every
POST. Never publish or log the token. Requests must use the server's loopback
Host and, when supplied, a same-loopback Origin. Cross-site requests are rejected;
there is no CORS access or remote-server mode.

| Method & route | Request | Response |
|---|---|---|
| `GET /api/config` | — | `token`, `version`, `ffmpegAvailable`, `dataDir` |
| `POST /api/setup` | `{}` | Explicit direct-from-PyPI FFmpeg setup; `ok`, `ffmpeg` |
| `POST /api/import?name=filename.mp4` | Raw video bytes, Content-Length | Probed clip; persisted media copy |
| `POST /api/probe` | `{"path":"absolute/local/file.mp4"}` | Probed clip; registers preview access |
| `POST /api/project` | Project JSON | Validated project; registers preview access |
| `GET /api/media?path=...` | URL-encoded registered path | Media bytes; supports a single byte range |
| `POST /api/export` | Project JSON | HTTP 202, `{"id":"job-id"}` |
| `GET /api/jobs/job-id` | — | `id`, `status`, `progress`, optional `error` or `download` |
| `POST /api/cancel` | `{"id":"job-id"}` | `{"ok":true}` |
| `GET /api/download/job-id` | Completed job | MP4 attachment |

Jobs are in-memory for one launcher session. Status is `running`, `done`, or
`error`; cancelled jobs use `error` with a cancellation message. Completed files
remain in local storage after restart, but old job URLs do not. Errors return
`{"error":"actionable message"}`. There is one concurrent export per server.

Projects and source media are trusted local input: opening a project authorizes
reading its referenced files through FFmpeg. Only open projects/media from
sources you trust. The server is not a hardened public upload/transcoding service.
