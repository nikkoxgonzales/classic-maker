# Changelog

## 0.2.0 — 2026-10-12

- Interactive three-track timeline: proportional Video, Audio, and Effects lanes
  with a ruler, draggable playhead, clip thumbnails, and zoom.
- Drag to reorder/trim/place, split video and audio at the playhead, seek by
  clicking, keyboard transport (Space, arrows, Home/End), and undo/redo.
- Independent audio clips: music/voice placed anywhere in the movie with volume
  and mute, mixed additively with a limiter; original video sound can be muted
  or detached to its own editable clip.
- Static timed effects — Brightness, Contrast, Grayscale, Sepia — over exact
  movie-time ranges, live in preview and in export. Still no animations or
  transitions.
- Project format v2 (`tracks.video/audio/effects`); v1 projects migrate on open.
  Versioned JSON remains readable by agents and the CLI.
- Audio-only media import, first-frame thumbnails, and synchronized preview
  across clip boundaries.
- FFmpeg pipeline now uses PCM/NUT intermediates for frame-exact cuts, applies
  effects per clip, and mixes audio in one final pass (works even on FFmpeg
  builds without `-filter_complex_script`).

## 0.1.0 — 2026-10-12

- Initial Classic Maker: a lightweight local FFmpeg video editor inspired by
  Windows Movie Maker, created by Nikko Gonzales.
- Dark interface, original film/play logo, beginner guidance, and About attribution.
- Import video clips, trim by seconds/playhead, reorder, mute, remove, and preview.
- 720p/1080p H.264/AAC MP4 exports with progress, cancellation, consistent aspect
  fitting, and silent-source handling. No animations, transitions, or effects.
- Save/open versioned JSON projects; probe/render/doctor/local-server CLI.
- User-requested verified FFmpeg setup, portable Python-runtime builds, public
  usage/architecture/automation/development docs, and real-media regression tests.
