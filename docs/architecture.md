# Architecture

Classic Maker is a Python standard-library app serving plain HTML/CSS/JavaScript
on loopback. A browser handles the interface and native source-video playback.
FFmpeg handles probing and export. There is no Electron shell, Node runtime,
frontend build step, database, or cloud backend.

| Module | Responsibility |
|---|---|
| `classic_maker/__main__.py` | CLI dispatch, launcher, JSON stdout, error exit codes |
| `classic_maker/media.py` | FFmpeg resolution/probe, v2 track validation + v1 migration, per-clip effect/transcode, audio mix, cancellation |
| `classic_maker/server.py` | Local HTTP boundary, persistent imports, range streaming, thumbnails, async export jobs |
| `classic_maker/settings.py` | Platform-native user storage directory |
| `classic_maker/setup.py` | User-requested HTTPS FFmpeg wheel download and SHA-256 verification |
| `classic_maker/web/` | Three-track timeline UI, playback sync, project state, About, original SVG logo |
| `scripts/build_portable.py` | PyInstaller archive with Python runtime and local UI, not FFmpeg |
| `tests/test_media.py` | Real-FFmpeg consumer-visible media regressions |

## Data flow

1. Browser imports stream to unique local `media/` files, without loading a whole
   source video into server memory. FFmpeg reads metadata (video or audio) and
   first-frame thumbnails; the UI gets a clip.
2. Edits live in browser memory across three tracks: contiguous video, positioned
   audio, and timed static effects. Save project serializes v2 JSON; open project
   re-probes every distinct source and migrates v1 projects before accepting edits.
3. Preview streams registered sources with HTTP byte-range support. Native video
   playback is synchronized to a global movie clock; independent audio elements
   and CSS filters follow the same clock, pausing during video buffering rather
   than drifting ahead.
4. Export takes a validated snapshot and transcodes each video trim to H.264 +
   PCM audio in a NUT temporary file, applying that clip's overlapping effects in
   clip-local time (movie time minus clip start). Missing/muted audio becomes
   silence. Every clip fits the same canvas, frame rate, audio rate, and channels.
5. A generated concat list with declared trim durations joins clips. Independent
   audio clips are normalized to PCM WAVs first (one input each, keeping the
   command line small), then mixed at their movie offsets with `amix` and a
   limiter. The final pass enforces exact 30 fps video and encodes AAC.
   Only a complete result is published; `+faststart` moves MP4 metadata forward.
6. The browser polls an in-memory job for progress and downloads the completed
   output. The CLI calls the same renderer synchronously.

## Invariants

- Source files are never changed. Existing output replacement is explicit.
- Video clip array order defines the contiguous picture timeline; audio `at` and
  effect `at`/`duration` are movie-time positions. Effects are static holds, never
  animated; no transitions or CSS/JS UI animations.
- Derived metadata is re-read from media, not trusted from project JSON.
- FFmpeg receives argument arrays, never shell commands. Input paths are local;
  FFmpeg's input protocol whitelist excludes network fetching.
- Generated concat filenames are simple, relative, and untrusted paths never
  become concat-list syntax.
- One export runs per local server. The worker is non-daemon so normal shutdown
  cancellation can stop FFmpeg and clean work before Python exits.
- Long stderr logs go to disk, not an undrained pipe. A cancellation watcher can
  stop FFmpeg even when progress output stalls.
- HTTP binds only to `127.0.0.1`, checks Host/Origin/Fetch-Site, requires a random
  per-session token for mutations, sets a strict same-origin CSP, and has no CORS.
- Only imported, probed, or validated project sources may be previewed. There is
  no arbitrary static file serving or directory traversal.
- Imported copies and complete exports are persistent; jobs and browser edits
  are not. Automatic deletion could break saved projects and is intentionally absent.

## Limits

This is a desktop-local application, not a hostile-client internet service.
Local processes can access it; possession of the session token permits local
file probing. Media parsers must be kept updated, and inputs should be trusted.
FFmpeg stderr metadata parsing avoids requiring a separate ffprobe executable;
unsupported/unknown-duration videos fail with an explicit error. Export costs
CPU and disk space roughly proportional to the selected clips, independent of
the small application's footprint.
