# Architecture

Classic Maker is a Python standard-library app serving plain HTML/CSS/JavaScript
on loopback. A browser handles the interface and native source-video playback.
FFmpeg handles probing and export. There is no Electron shell, Node runtime,
frontend build step, database, or cloud backend.

| Module | Responsibility |
|---|---|
| `classic_maker/__main__.py` | CLI dispatch, launcher, JSON stdout, error exit codes |
| `classic_maker/media.py` | FFmpeg resolution/probe, project validation, cut/normalize/concat, cancellation |
| `classic_maker/server.py` | Local HTTP boundary, persistent imports, range streaming, async export jobs |
| `classic_maker/settings.py` | Platform-native user storage directory |
| `classic_maker/setup.py` | User-requested HTTPS FFmpeg wheel download and SHA-256 verification |
| `classic_maker/web/` | UI, browser project state, native video preview, storyboard, About, original SVG logo |
| `scripts/build_portable.py` | PyInstaller archive with Python runtime and local UI, not FFmpeg |
| `tests/test_media.py` | Real-FFmpeg consumer-visible media regressions |

## Data flow

1. Browser imports stream to unique local `media/` files, without loading a whole
   source video into server memory. FFmpeg reads metadata; the UI gets a clip.
2. Edits live in browser memory. Save project serializes the v1 JSON format.
   Open project re-probes every distinct source before accepting its trims.
3. Preview streams registered sources with HTTP byte-range support. Native
   playback uses source codecs and trim boundaries; sequential preview switches
   sources rather than encoding a temporary preview movie.
4. Export takes a validated snapshot and transcodes each trim to matching H.264
   video and AAC audio in a temporary directory. Missing/muted audio becomes
   silence. Every clip fits the same canvas, frame rate, audio rate, and channels.
5. A generated concat list joins normalized clips. A final video encode enforces
   even 30 fps spacing despite AAC packet-tail timing; audio is copied. This costs
   a second video pass but avoids unsafe overlapping packet timestamps.
   `+faststart` moves MP4 metadata forward. Only a complete result is published.
6. The browser polls an in-memory job for progress and downloads the completed
   output. The CLI calls the same renderer synchronously.

## Invariants

- Source files are never changed. Existing output replacement is explicit.
- Clip array order, trim seconds, and mute state define the movie.
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
- No CSS/JS animations or effects. Keep the primary workflow small.

## Limits

This is a desktop-local application, not a hostile-client internet service.
Local processes can access it; possession of the session token permits local
file probing. Media parsers must be kept updated, and inputs should be trusted.
FFmpeg stderr metadata parsing avoids requiring a separate ffprobe executable;
unsupported/unknown-duration videos fail with an explicit error. Export costs
CPU and disk space roughly proportional to the selected clips, independent of
the small application's footprint.
