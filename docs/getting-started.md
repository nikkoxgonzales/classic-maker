# Your first movie

## Open the editor

Download the ZIP for your OS from [Releases](https://github.com/nikkoxgonzales/classic-maker/releases/latest).
Extract **all** of it; the `_internal` folder must stay beside the executable.
The ZIP is portable: it doesn't install a service or ask for administrator access.

### Windows

Open `classic-maker.exe`. Keep the console window open while editing. The editor
opens in your default browser. The original film/play icon identifies the app.
Unsigned new software can trigger SmartScreen. Verify the release URL and checksum
before deciding whether to run it; don't disable SmartScreen globally.

### macOS

Download the asset matching your Mac: `arm64` for Apple silicon, `x86_64` for Intel.
Open Terminal, type `cd `, drag the extracted `classic-maker` folder into the
window, and press Return. Run:

```sh
chmod +x classic-maker
./classic-maker
```

These binaries are not signed or notarized. If macOS blocks the app, review it in
System Settings → Privacy & Security rather than turning off Gatekeeper globally.
The Python source-install route in the README is another option.

### Linux

Use a glibc-based desktop distribution (portable x64 builds use Ubuntu 22.04).
In Terminal, open the extracted folder and run:

```sh
chmod +x classic-maker
./classic-maker
```

Minimal installations may need your distro's OpenSSL/zlib libraries. Alpine/musl
and other architectures should use Python plus their system FFmpeg package.

### One-time FFmpeg setup

If FFmpeg isn't already available, the editor displays **Set up FFmpeg**. Click it
once. The app downloads an imageio-ffmpeg 0.6.0 wheel directly from PyPI, verifies
its SHA-256 hash, and keeps the FFmpeg executable in local app storage. It does not
install the Python wrapper. Allow about 20–31 MB of download and 45–85 MB on disk.
If this fails, check internet access or install FFmpeg with your OS package manager.

Normal editing and exporting work offline after setup. No media is sent to PyPI.

## Import → arrange → play → export

The editor has three lanes: **Video** (top), **Audio** (middle), and **Effects**
(bottom), with a time ruler and a draggable playhead.

1. Click **Import media** for video files, or **Add audio** for music/voice.
   You can also drag files from the media list (or straight from your file
   manager onto a lane).
2. **Video lane:** clips play back-to-back in order. Drag a clip sideways to
   reorder, drag its left/right edges to trim, or click **✂ Split** with the
   playhead inside a clip (keyboard: `S`). Selected clips open numeric controls
   on the right — every drag has a typed alternative.
3. **Audio lane:** each video shows a linked `♪` strip for its original sound
   (click to edit that video). Use **Detach audio to its own clip** to pull sound
   out and move it freely. Music/voice blocks have `at` (movie position),
   source trim, volume, and mute.
4. **Effects lane:** pick Brightness/Contrast/Grayscale/Sepia, click **＋ Effect**,
   then drag the block and adjust amount, start, and duration on the right.
   Effects hold for their range — there are no animations or transitions.
5. **Play** follows the timeline across clips; `Space` toggles play, arrow keys
   step frames, `Ctrl+Z` / `Ctrl+Shift+Z` undo and redo. The clock pauses while
   a video loads so audio and picture don't drift apart.
6. Choose **720p** or **1080p**, click **Export movie**, wait, then **Download
   your movie**. The result is H.264/AAC MP4 at exact 30 fps with all three
   tracks combined.

Only one export runs at a time. Cancel stops encoding and removes temporary work;
your originals and any previous output are unchanged. Editing during export does
not change the in-progress movie—the export uses a snapshot.

## Projects are not movies

**Save project** downloads a `.classic-maker.json` file containing source paths,
clip order, trims, mute settings, name, and export quality. Use **Open project**
to continue later on the same computer. The JSON does **not** contain videos.

To move a project to another computer, copy its referenced media as well and
update the paths. For portable automation, use relative paths and the CLI; see
[project format](project-format.md). Browser project loading expects absolute paths.

Unsaved edits are kept only in the page. Refreshing or closing the browser loses
them; the editor asks before leaving a dirty project. Save before quitting.

## Where your files live

| OS | Default app data directory |
|---|---|
| Windows | `%LOCALAPPDATA%\classic-maker` |
| macOS | `~/Library/Application Support/classic-maker` |
| Linux | `$XDG_DATA_HOME/classic-maker`, or `~/.local/share/classic-maker` |

- `media/`: persistent imported copies. Saved projects refer to these files.
- `exports/`: completed movie copies, even after downloading them.
- `tools/`: FFmpeg from one-time setup, when used.
- Saved projects and downloaded movies go to your browser's download location.
- Temporary encoding files live beside the export destination and are removed on
  normal completion/cancellation. Force-killing the app can leave a temporary folder.

Nothing is deleted automatically. To reclaim space, quit the app, back up needed
projects/media/movies, then delete only the copies you no longer need. Deleting
`media/` breaks projects referencing it. Override the root with `CLASSIC_MAKER_DATA`.

## Troubleshooting

- **The browser didn't open:** copy the local URL printed in the launcher window.
- **The page can't connect:** keep the launcher running, then reload the page.
- **A codec cannot preview:** native browser codec support is limited. H.264 MP4
  is the safest preview format. Trim by seconds and try exporting through FFmpeg.
- **A project can't find a clip:** restore the referenced path or edit the JSON.
- **FFmpeg can't start:** run `python -m classic_maker doctor` (or the portable
  executable with `doctor`). Set `CLASSIC_MAKER_FFMPEG` to a trusted executable's
  full path to override detection. Use a build with libx264 and AAC support.
- **Export fails:** read the shown FFmpeg error; check free disk space and media
  readability. Leave room for per-clip transcodes plus the final movie.
- **Existing CLI output:** choose another filename or explicitly pass `--overwrite`.
- **Network restrictions:** setup contacts only PyPI/files.pythonhosted.org.
  Install FFmpeg manually if those sites are unavailable; no setup network is
  required when a supported FFmpeg is already installed.
