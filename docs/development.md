# Development

Python 3.10+ and FFmpeg with libx264/AAC are required. Node is only optional for
checking JavaScript syntax; it is not an app dependency.

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[bundled]"
python -m classic_maker
```

There is no frontend build. HTML/CSS/JS are package data; refresh the browser for
frontend edits and restart the launcher for Python edits.

## Verify behavior

```sh
python -m unittest discover -s tests -v
python -m classic_maker doctor
python -m classic_maker serve --no-browser --port 8765
```

The fourteen real-FFmpeg/HTTP tests check trim/reorder, mixed portrait/silent
media, retained audio, mute, invalid/nonfinite trims, relative paths, original
preservation, overwrite precedence, cancellation cleanup, even frame spacing
across cuts, v1→v2 migration, audio-only probing, audio placement/gain mixing,
timed effect ranges, and shutdown racing a pending export. They create small
isolated videos/audio in temporary directories. Optional system ffprobe adds
resolution and frame-rate assertions; the app itself does not require ffprobe.

After UI or media changes, **also run the real editor**:

1. Import two videos (one silent/portrait) plus an MP3 via Add audio.
2. Drag-reorder video clips, drag trim edges, split at the playhead (S), and
   confirm the ruler/playhead/zoom and undo/redo behave.
3. Detach one clip's sound, move the audio block, and change its volume; confirm
   linked source-sound strips follow their video clips.
4. Add a Grayscale effect, drag its range, and watch the preview filter change
   only while the playhead is inside it.
5. Play across a clip boundary: clock, preview label, and independent audio stay
   in sync; pause during a brief load and confirm no drift.
6. Save the project (v2 JSON with tracks), reload, reopen, and check every lane.
7. Export 720p and 1080p; download and verify with `ffprobe`: duration matches
   the video-track total, CFR 30/1, H.264+AAC, effects visible only in their
   range, audio present at its offset, originals unchanged.
8. Cancel an export; verify no completed output is offered.
9. Check keyboard shortcuts, narrow layout, empty states, and About attribution.
10. Use the saved project with CLI `render`. Confirm stdout JSON and a playable MP4.

A passing unit suite or syntax check alone is not proof of a working editor.
Keep permanent tests focused on behavior/boundaries, not copied implementation
strings or forwarding. Use temporary smoke scripts for wiring checks.

## Portable builds

```sh
python -m pip install pyinstaller
python scripts/build_portable.py
```

Build on the target OS/architecture. Output is
`dist/classic-maker-0.1.0-<os>-<architecture>.zip`. It contains a Python runtime,
web assets, logo, documentation, license, and notices. It explicitly excludes
imageio-ffmpeg, so no FFmpeg binary is redistributed. One-time in-app setup obtains
FFmpeg directly from PyPI; an existing system installation also works.

Before publishing, launch the built executable, use its first-run FFmpeg setup,
import clips, and export/download a movie. Build smoke should run `doctor` and
CLI rendering too, not merely check that an executable exists.

GitHub Actions runs the regression suite on Windows, Linux, and macOS and builds
portable archives. A `v*` tag creates a release only when all matrix jobs succeed.
Release binaries are unsigned; do not imply code signing or notarization.

## Packaging & licensing

The original app and logo are GPL-3.0-or-later. Python/PyInstaller notices and
FFmpeg acquisition/licensing are described in [THIRD_PARTY.md](../THIRD_PARTY.md).
Changing the distribution to include FFmpeg requires satisfying that exact
binary's corresponding-source and notice obligations.

Update the README and relevant `docs/` sections in the same change as behavioral
changes. [Architecture](architecture.md) describes the boundaries; [project
format](project-format.md) is the automation contract. Keep edits understandable:
one media engine for HTTP and CLI, no unnecessary frameworks or abstractions.
