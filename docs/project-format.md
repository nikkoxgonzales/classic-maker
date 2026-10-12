# Projects, CLI, and local API

Classic Maker uses readable versioned JSON. Version 2 separates the movie into
three tracks; there is no hidden database or UI state needed to render a project.

## Project format v2

```json
{
  "version": 2,
  "name": "A weekend away",
  "tracks": {
    "video": [
      {"id": "v1", "path": "videos/arrival.mp4", "name": "Arrival",
       "start": 0.5, "end": 5.0, "muted": false, "volume": 1.0}
    ],
    "audio": [
      {"id": "a1", "path": "music/song.mp3", "name": "song.mp3",
       "at": 2.0, "start": 0.0, "end": 6.0, "muted": false, "volume": 0.7}
    ],
    "effects": [
      {"id": "e1", "type": "grayscale", "at": 3.0, "duration": 1.5, "value": 1}
    ]
  },
  "output": {"resolution": "720p", "fps": 30}
}
```

- `version` is `2`. Version-1 projects (`clips` array) are still accepted and
  migrate to tracks on validation/open; saved projects are always v2.
- **Video track:** clips are contiguous and ordered by array position — clip `i+1`
  starts where clip `i` ends; there are no gaps or video overlays. Maximum 1,000.
- **Audio track:** each clip has `at` (movie seconds where it starts), `start`/
  `end` (source trim), `volume` 0–1, and `muted`. Clips may overlap; overlapping
  audio is mixed additively and limited to avoid clipping. Maximum 64. Audio must
  reference a source with an audio stream. Detached video sound keeps `videoId`.
- **Effects track:** `type` is `brightness` (-1..1), `contrast` (0..2),
  `grayscale` (0..1), or `sepia` (0..1); `at` is movie seconds, `duration` > 0.
  Maximum 256. Overlapping effects apply in array order. Effects are static
  (held for their range), never animated or transitioned.
- Movie duration is the sum of video clip lengths. Audio/effects beyond that
  end remain in the project but are clipped out of preview and export.
- `path` is a local file, not a URL. CLI relative paths resolve against the JSON
  file's directory; browser-created projects use absolute storage paths.
- `start`/`end` are finite source seconds with `0 ≤ start < end ≤ source
  duration`. All time fields are rounded to 0.01 s in saved projects.
- `id` identifies an item; missing/duplicate IDs are regenerated on validation.
- Derived `duration`/`hasAudio`/`kind` are recomputed from the source, never
  trusted as project instructions.
- `output.resolution` is `720p` or `1080p`; `fps` is `30`. Exports are 16:9
  H.264/AAC MP4 with black-bar fitting and square pixels.

### Example (CLI)

```json
{
  "version": 2,
  "name": "Holiday",
  "tracks": {
    "video": [{"path": "holiday.mp4", "start": 1.0, "end": 6.0}],
    "audio": [],
    "effects": [{"type": "brightness", "at": 0, "duration": 2, "value": 0.2}]
  },
  "output": {"resolution": "720p", "fps": 30}
}
```

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

- `probe`: JSON clip plus `kind` (`video`/`audio`), source duration, and audio
  availability on stdout.
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
project = {"version": 2, "name": "Holiday",
           "tracks": {"video": [clip], "audio": [], "effects": []},
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
| `POST /api/import?name=filename.mp4` | Raw video/audio bytes, Content-Length | Probed clip with `kind`; persisted media copy |
| `POST /api/probe` | `{"path":"absolute/local/media"}` | Probed clip; registers preview access |
| `POST /api/project` | Project JSON (v1 or v2) | Validated v2 project; registers video/audio paths |
| `GET /api/media?path=...` | URL-encoded registered path | Media bytes; supports a single byte range |
| `GET /api/thumbnail?path=...` | URL-encoded registered video path | 160×90 PNG frame, cached by file identity |
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
