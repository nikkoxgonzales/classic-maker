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

The nine real-FFmpeg/HTTP tests check trim/order and mixed portrait/silent media,
retained audio, mute, invalid/nonfinite trims, relative project paths, original
preservation, overwrite precedence, cancellation cleanup, even frame spacing
across cuts, and shutdown racing with a pending export request. They create small
isolated videos in temporary directories. Optional system ffprobe adds resolution
and frame-rate assertions; the app itself does not require ffprobe.

After UI or media changes, **also run the real editor**:

1. Import a landscape clip with audio and a silent portrait clip.
2. Trim, move a clip earlier/later, and mute a clip.
3. Play movie: selected clips advance in storyboard order and stop at their trims.
4. Save a project, remove a clip, reopen the saved project, and check edits survived.
5. Export 720p and 1080p; download and play the MP4. Check duration, order, sound,
   fit/black bars, and that originals are unchanged.
6. Cancel an export; verify no completed output is offered.
7. Check About attribution, keyboard navigation, empty state, and narrow layout.
8. Use the saved project with CLI `render`. Confirm stdout JSON and a playable MP4.

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
