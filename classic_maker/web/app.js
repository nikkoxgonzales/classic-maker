'use strict';
/* Classic Maker — three-track editor: Video, Audio, Effects. No frameworks. */
const $ = id => document.getElementById(id);
const player = $('player');

let project = {version: 2, name: 'My first movie', tracks: {video: [], audio: [], effects: []}, output: {resolution: '720p', fps: 30}};
let token = '', dirty = false, importing = false, jobId = null;
let time = 0, playing = false, loadingToken = 0, loadedClipId = null;
let zoom = 80, selection = null;           // selection = {lane, id}
const undoStack = [], redoStack = [];
let gestureKey = null;

const MIN_CLIP = 0.05;
const mediaUrl = path => '/api/media?path=' + encodeURIComponent(path);
const thumbUrl = path => '/api/thumbnail?path=' + encodeURIComponent(path);
const fmt = (s, tenths = true) => {
  s = Math.max(0, s || 0);
  const m = Math.floor(s / 60), sec = s - m * 60;
  return `${String(m).padStart(2, '0')}:${tenths ? sec.toFixed(2).padStart(5, '0') : String(Math.round(sec)).padStart(2, '0')}`;
};
const round = n => Math.round(n * 100) / 100;
const uid = () => Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
const notice = (text, error = false) => { $('notice').textContent = text; $('notice').classList.toggle('error', error); };

async function api(path, body, raw = false) {
  const options = body === undefined ? {} : {method: 'POST', headers: {'X-Classic-Maker-Token': token}, body: raw ? body : JSON.stringify(body)};
  if (body !== undefined && !raw) options.headers['Content-Type'] = 'application/json';
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
  return data;
}

/* ---------- history ---------- */
function pushUndo() { undoStack.push(JSON.stringify(project)); if (undoStack.length > 100) undoStack.shift(); redoStack.length = 0; gestureKey = null; }
function beginGesture(key) { if (gestureKey === key) return; pushUndo(); gestureKey = key; }
function endGesture() { gestureKey = null; dirty = true; update(); }
function commit(fn) { pushUndo(); fn(); dirty = true; update(); }
function restore(json) { project = JSON.parse(json); selection = null; dirty = true; time = Math.min(time, movieDuration()); stop(); update(); }
function undo() { if (!undoStack.length) return; redoStack.push(JSON.stringify(project)); restore(undoStack.pop()); }
function redo() { if (!redoStack.length) return; undoStack.push(JSON.stringify(project)); restore(redoStack.pop()); }

/* ---------- model ---------- */
const movieDuration = () => project.tracks.video.reduce((sum, c) => sum + (c.end - c.start), 0);
function videoLayout() { let at = 0; return project.tracks.video.map(clip => { const row = {clip, at, len: clip.end - clip.start}; at += row.len; return row; }); }
function videoAt(t) {
  const rows = videoLayout();
  if (!rows.length) return null;
  for (const row of rows) if (t < row.at + row.len - 1e-6) return {...row, local: Math.max(0, t - row.at)};
  const last = rows[rows.length - 1];
  return {...last, local: last.len};
}
function activeEffects(t) {
  return project.tracks.effects.filter(e => t >= e.at && t < e.at + e.duration)
    .sort((a, b) => project.tracks.effects.indexOf(a) - project.tracks.effects.indexOf(b));
}
function findItem(lane, id) { return project.tracks[lane].find(x => x.id === id) || null; }
function selected() { return selection ? findItem(selection.lane, selection.id) : null; }

/* ---------- undo-safe mutations ---------- */
function addToVideo(clip, index) { commit(() => { clip.id = uid(); project.tracks.video.splice(index ?? project.tracks.video.length, 0, clip); }); }
function addToAudio(clip, at) { commit(() => { clip.id = uid(); clip.at = round(Math.max(0, at ?? time)); project.tracks.audio.push(clip); }); }

/* ---------- snapshot & update ---------- */
function update() {
  const duration = movieDuration();
  const currentVideo = videoAt(time);
  $('preview-label').textContent = currentVideo ? currentVideo.clip.name : 'No video yet';
  $('clip-count').textContent = project.tracks.video.length + project.tracks.audio.length + project.tracks.effects.length;
  $('library-empty').hidden = project.tracks.video.length + project.tracks.audio.length > 0;
  const hasVideo = project.tracks.video.length > 0;
  $('preview-empty').hidden = hasVideo;
  ['jump-start', 'play-movie', 'step-back', 'step-forward', 'seek-bar', 'add-effect'].forEach(id => { $(id).disabled = !hasVideo || importing || !!jobId; });
  $('export-button').disabled = !hasVideo || importing || !!jobId || !token;
  ['save-button', 'open-button', 'import-button', 'audio-import', 'empty-import'].forEach(id => { $(id).disabled = importing || !!jobId || !token; });
  $('undo').disabled = !undoStack.length; $('redo').disabled = !redoStack.length;
  $('total-duration').textContent = fmt(duration);
  $('seek-bar').max = Math.max(0.01, duration);
  $('seek-bar').value = Math.min(time, duration);
  $('play-movie').textContent = playing ? '❚❚ Pause' : '▶ Play';
  $('playhead-time').textContent = fmt(time);
  $('timeline-hint').textContent = hasVideo
    ? `${project.tracks.video.length} video · ${project.tracks.audio.length} sound · ${project.tracks.effects.length} effect${project.tracks.effects.length === 1 ? '' : 's'}`
    : 'Import or drop a video to set your movie length. Music and effects can then be placed anywhere.';
  renderLibrary(); renderTimeline(); renderInspector(); renderEffectsFilter();
  $('playhead').style.left = (time * zoom) + 'px';
  $('movie-end').style.left = (duration * zoom) + 'px';
}

function renderLibrary() {
  const list = $('clip-list'); list.textContent = '';
  const seen = new Set();
  const sources = [...project.tracks.video, ...project.tracks.audio].filter(c => { if (seen.has(c.path)) return false; seen.add(c.path); return true; });
  sources.forEach(src => {
    const item = document.createElement('div');
    item.className = 'library-item'; item.draggable = true; item.dataset.path = src.path;
    if (src.kind === 'video') {
      const img = document.createElement('img'); img.alt = ''; img.loading = 'lazy'; img.src = thumbUrl(src.path);
      img.onerror = () => { const span = document.createElement('span'); span.className = 'media-icon'; span.textContent = '▤'; item.replaceChild(span, img); };
      item.append(img);
    } else {
      const span = document.createElement('span'); span.className = 'media-icon'; span.textContent = '♫'; item.append(span);
    }
    const meta = document.createElement('span'); meta.className = 'clip-meta';
    const strong = document.createElement('strong'); strong.textContent = src.name; strong.title = src.name;
    const small = document.createElement('small'); small.textContent = `${src.kind === 'video' ? 'video' : 'audio'} · ${fmt(src.duration)}`;
    meta.append(strong, small); item.append(meta);
    const add = document.createElement('button'); add.className = 'library-add'; add.textContent = '＋'; add.title = 'Add to timeline'; add.disabled = importing;
    add.onclick = () => { src.kind === 'video' ? addToVideo({path: src.path, name: src.name, start: 0, end: src.duration, muted: false, volume: 1, duration: src.duration, hasAudio: src.hasAudio, kind: 'video'}) : addToAudio({path: src.path, name: src.name, start: 0, end: src.duration, muted: false, volume: 1, duration: src.duration, hasAudio: true, kind: 'audio'}); };
    item.append(add);
    item.addEventListener('dragstart', e => e.dataTransfer.setData('text/classic-maker', JSON.stringify({source: {path: src.path, name: src.name, kind: src.kind, duration: src.duration, hasAudio: src.hasAudio}})));
    list.append(item);
  });
}

/* ---------- timeline ---------- */
function blockBase(el, lane, item) {
  el.className += ' lane-block' + (selection && selection.lane === lane && selection.id === item.id ? ' selected' : '');
  el.dataset.lane = lane; el.dataset.id = item.id;
  const left = document.createElement('span'); left.className = 'trim-handle left'; left.dataset.handle = 'left';
  const right = document.createElement('span'); right.className = 'trim-handle right'; right.dataset.handle = 'right';
  const text = document.createElement('span'); text.className = 'block-text';
  el.append(left, text, right);
  return text;
}
function renderTimeline() {
  const duration = movieDuration();
  const world = $('timeline-world');
  world.style.width = Math.max($('timeline-scroll').clientWidth, duration * zoom + 60) + 'px';

  /* ruler */
  const ruler = $('ruler'); ruler.textContent = '';
  const steps = [0.2, 0.5, 1, 2, 5, 10, 30, 60];
  const step = steps.find(s => s * zoom >= 55) || 60;
  for (let s = 0; s <= duration + step; s += step) {
    const tick = document.createElement('div'); tick.className = 'ruler-tick'; tick.style.left = (s * zoom) + 'px';
    const label = document.createElement('span'); label.textContent = fmt(s, step < 1); tick.append(label);
    ruler.append(tick);
  }

  /* video lane */
  const lane = $('video-lane'); lane.textContent = '';
  if (!project.tracks.video.length) lane.append(hint('Drop or add a video clip — video clips play back-to-back.'));
  videoLayout().forEach((row, i) => {
    const el = document.createElement('div'); el.style.left = (row.at * zoom) + 'px'; el.style.width = Math.max(4, row.len * zoom) + 'px';
    const text = blockBase(el, 'video', row.clip);
    const img = document.createElement('img'); img.alt = ''; img.loading = 'lazy'; img.src = thumbUrl(row.clip.path);
    img.onerror = () => img.remove(); el.insertBefore(img, text);
    const strong = document.createElement('strong'); strong.textContent = `${i + 1}. ${row.clip.name}`; strong.title = row.clip.name;
    const small = document.createElement('small'); small.textContent = `${fmt(row.clip.start)} → ${fmt(row.clip.end)}${row.clip.muted || !row.clip.hasAudio ? ' · muted' : ''}`;
    text.append(strong, small); lane.append(el);
  });

  /* audio lane: linked source audio (derived) + independent clips */
  const alane = $('audio-lane'); alane.textContent = '';
  videoLayout().forEach(row => {
    if (!row.clip.hasAudio) return;
    const el = document.createElement('div');
    el.className = 'lane-block linked-audio' + (row.clip.muted ? ' muted' : '');
    el.style.left = (row.at * zoom) + 'px'; el.style.width = Math.max(4, row.len * zoom) + 'px';
    el.title = row.clip.muted ? 'Video sound is muted' : 'Original video sound — click to edit its video clip';
    el.dataset.lane = 'video'; el.dataset.id = row.clip.id;
    const text = document.createElement('span'); text.className = 'block-text';
    const strong = document.createElement('strong'); strong.textContent = row.clip.muted ? `🔇 ${row.clip.name}` : `♪ ${row.clip.name}`;
    const small = document.createElement('small'); small.textContent = `${Math.round((row.clip.volume ?? 1) * 100)}%`;
    text.append(strong, small); el.append(text);
    el.addEventListener('pointerdown', e => { if (e.target === el || e.target.closest('.block-text')) { e.stopPropagation(); select('video', row.clip.id); } });
    alane.append(el);
  });
  project.tracks.audio.forEach(clip => {
    const start = clip.at, len = Math.min(clip.end - clip.start, duration > 0 ? duration - clip.at : clip.end - clip.start);
    const el = document.createElement('div');
    el.style.left = (start * zoom) + 'px'; el.style.width = Math.max(4, len * zoom) + 'px';
    const text = blockBase(el, 'audio', clip);
    el.classList.add('audio-block');
    const strong = document.createElement('strong'); strong.textContent = `♫ ${clip.name}`; strong.title = clip.name;
    const small = document.createElement('small'); small.textContent = `${Math.round((clip.volume ?? 1) * 100)}%${clip.muted ? ' · muted' : ''}`;
    text.append(strong, small); alane.append(el);
  });
  if (!project.tracks.audio.length && !project.tracks.video.some(c => c.hasAudio)) alane.append(hint('Add music or a voice recording — it can start anywhere in the movie.'));

  /* effects lane */
  const elane = $('effects-lane'); elane.textContent = '';
  project.tracks.effects.forEach(effect => {
    const el = document.createElement('div');
    const text = blockBase(el, 'effects', effect);
    el.classList.add('effect-block');
    el.style.left = (effect.at * zoom) + 'px'; el.style.width = Math.max(6, effect.duration * zoom) + 'px';
    const strong = document.createElement('strong'); strong.textContent = effectLabel(effect);
    const small = document.createElement('small'); small.textContent = `${fmt(effect.at)} +${effect.duration}s`;
    text.append(strong, small); elane.append(el);
  });
  if (!project.tracks.effects.length) elane.append(hint('Choose an effect above, then drag its range in the movie.'));
}
function hint(text) { const el = document.createElement('span'); el.className = 'lane-hint'; el.textContent = text; return el; }
function effectLabel(e) {
  const map = {brightness: 'Brightness', contrast: 'Contrast', grayscale: 'Grayscale', sepia: 'Sepia'};
  const value = e.type === 'grayscale' || e.type === 'sepia' ? `${Math.round(e.value * 100)}%` : e.type === 'contrast' ? `${e.value.toFixed(2)}×` : e.value.toFixed(2);
  return `${map[e.type]} ${value}`;
}

/* ---------- selection & inspector ---------- */
function select(lane, id) {
  const changedSelection = !selection || selection.id !== id || selection.lane !== lane;
  selection = {lane, id};
  if (lane === 'video' && changedSelection) {
    const row = videoLayout().find(r => r.clip.id === id);
    if (row) seek(row.at + Math.min(0.001, row.len / 2), false);
  }
  update();
}
const EFFECT_LIMITS = {brightness: {min: -1, max: 1, step: 0.01}, contrast: {min: 0, max: 2, step: 0.01}, grayscale: {min: 0, max: 1, step: 0.01}, sepia: {min: 0, max: 1, step: 0.01}};
function renderInspector() {
  const item = selected();
  $('inspector-empty').hidden = !!item; $('selection-controls').hidden = !item;
  $('selection-kind').textContent = item ? selection.lane.toUpperCase() : '—';
  $('split').disabled = true;
  if (!item) return;
  const duration = movieDuration();
  $('selected-name').textContent = item.name || effectLabel(item);
  $('media-inspector').hidden = selection.lane === 'effects';
  $('effect-inspector').hidden = selection.lane !== 'effects';

  if (selection.lane === 'effects') {
    $('effect-type').value = item.type;
    $('effect-at').value = item.at; $('effect-duration').value = item.duration;
    const limits = EFFECT_LIMITS[item.type];
    Object.assign($('effect-value'), limits);
    $('effect-value').value = item.value;
    $('effect-value-label').textContent = item.type === 'brightness' ? item.value.toFixed(2) : item.type === 'contrast' ? item.value.toFixed(2) + '×' : Math.round(item.value * 100) + '%';
    return;
  }

  const row = videoLayout().find(r => r.clip.id === item.id);
  $('placement-row').hidden = selection.lane === 'video';
  if (selection.lane === 'audio') $('clip-at').value = item.at;
  $('trim-start').value = item.start.toFixed(2); $('trim-end').value = item.end.toFixed(2);
  $('trim-start').max = (item.duration - MIN_CLIP).toFixed(2); $('trim-end').max = item.duration.toFixed(2);
  $('trim-duration').textContent = `${(item.end - item.start).toFixed(2)}s source used${row ? ` · at ${fmt(row.at)}` : item.at !== undefined ? ` · at ${fmt(item.at)}` : ''}`;
  $('volume').value = Math.round((item.volume ?? 1) * 100);
  $('volume-value').textContent = `${$('volume').value}%`;
  $('mute').checked = !!item.muted;
  $('video-actions').hidden = selection.lane !== 'video';
  $('detach-audio').hidden = selection.lane !== 'video' || !item.hasAudio;
  $('move-left').disabled = project.tracks.video.findIndex(x => x.id === item.id) === 0;
  $('move-right').disabled = project.tracks.video.findIndex(x => x.id === item.id) === project.tracks.video.length - 1;
  let canSplit = false;
  if (selection.lane === 'video' && row) canSplit = time > row.at + MIN_CLIP && time < row.at + row.len - MIN_CLIP;
  if (selection.lane === 'audio') { const local = time - item.at; canSplit = local > MIN_CLIP && local < item.end - item.start - MIN_CLIP && local < movieDuration() - item.at - MIN_CLIP; }
  $('split').disabled = !canSplit;
  $('split-selected').disabled = !canSplit;
}
function renderEffectsFilter() {
  const values = {brightness: 1, contrast: 1, grayscale: 0, sepia: 0};
  activeEffects(time).forEach(e => {
    if (e.type === 'brightness') values.brightness = Math.max(0.05, 1 + e.value);
    if (e.type === 'contrast') values.contrast = e.value;
    if (e.type === 'grayscale') values.grayscale = e.value;
    if (e.type === 'sepia') values.sepia = e.value;
  });
  player.style.filter = `brightness(${values.brightness}) contrast(${values.contrast}) grayscale(${values.grayscale}) sepia(${values.sepia})`;
}

/* ---------- playback ---------- */
const audioElements = new Map();
function audioFor(clip) {
  let el = audioElements.get(clip.id);
  if (!el) { el = new Audio(); el.preload = 'auto'; el.src = mediaUrl(clip.path); audioElements.set(clip.id, el); }
  return el;
}
function loadVideo(clip, local, autoplay) {
  const tokenNow = ++loadingToken;
  loadedClipId = clip.id;
  $('buffering').hidden = false;
  player.src = mediaUrl(clip.path);
  player.volume = clip.muted ? 0 : (clip.volume ?? 1);
  const ready = () => {
    if (tokenNow !== loadingToken) return;
    player.currentTime = Math.min(Math.max(0, local), clip.end - 0.001);
    if (autoplay) player.play().catch(() => { playing = false; update(); });
  };
  if (player.readyState >= 1) ready(); else player.addEventListener('loadedmetadata', ready, {once: true});
}
function seek(t, autoplay = playing) {
  const duration = movieDuration();
  time = Math.min(Math.max(0, t), duration);
  const info = videoAt(time);
  if (info) {
    if (loadedClipId !== info.clip.id) loadVideo(info.clip, info.local, autoplay);
    else if (Math.abs(player.currentTime - (info.clip.start + info.local)) > 0.12 && !player.seeking) player.currentTime = info.clip.start + info.local;
    if (!autoplay) player.pause();
  }
  syncAudio(); update();
}
function stop() { playing = false; player.pause(); audioElements.forEach(el => el.pause()); update(); }
function togglePlay() {
  if (!project.tracks.video.length) return;
  if (playing) { stop(); return; }
  if (time >= movieDuration() - 0.01) seek(0);
  playing = true; update();
  const info = videoAt(time);
  if (info && loadedClipId !== info.clip.id) loadVideo(info.clip, info.local, true);
  else player.play().catch(() => { playing = false; update(); });
}
function syncAudio() {
  project.tracks.audio.forEach(clip => {
    const el = audioFor(clip);
    const inside = time >= clip.at && time < clip.at + (clip.end - clip.start);
    const want = inside ? clip.at + (time - clip.at) : -1;
    el.volume = clip.muted ? 0 : (clip.volume ?? 1);
    if (!inside) { el.pause(); return; }
    if (Math.abs(el.currentTime - want) > 0.3) { try { el.currentTime = want; } catch (_) {} }
    if (playing && el.paused) el.play().catch(() => {});
    if (!playing && !el.paused) el.pause();
  });
}
function frame() {
  const duration = movieDuration();
  if (playing) {
    const info = videoAt(time);
    if (info && loadedClipId === info.clip.id && !player.seeking && player.readyState >= 2) {
      const local = player.currentTime - info.clip.start;
      if (local >= info.clip.end - info.clip.start - 0.025) {
        const rows = videoLayout(), index = rows.findIndex(r => r.clip.id === info.clip.id);
        if (index < rows.length - 1) { const next = rows[index + 1]; loadVideo(next.clip, 0, true); time = next.at; }
        else { stop(); time = duration; }
      } else time = Math.max(0, info.at + local);
    } else if (player.readyState < 2) { $('buffering').hidden = false; }
    else $('buffering').hidden = true;
    syncAudio();
    const px = time * zoom, scroll = $('timeline-scroll');
    if (px > scroll.scrollLeft + scroll.clientWidth - 90) scroll.scrollLeft = px - scroll.clientWidth + 130;
  }
  $('playhead').style.left = (time * zoom) + 'px';
  $('playhead-time').textContent = fmt(time);
  const now = videoAt(time);
  if (now && $('preview-label').textContent !== now.clip.name) $('preview-label').textContent = now.clip.name;
  $('seek-bar').value = Math.min(time, duration);
  renderEffectsFilter();
  requestAnimationFrame(frame);
}

/* ---------- timeline gestures ---------- */
function snap(v) { return Math.round(v * 100) / 100; }
let drag = null;
function startDrag(e, mode) {
  const el = e.target.closest('.lane-block'); if (!el) return;
  const lane = el.dataset.lane, id = el.dataset.id, item = findItem(lane, id);
  if (!item) return;
  e.preventDefault(); e.stopPropagation();
  select(lane, id);
  const handle = e.target.dataset && e.target.dataset.handle;
  const row = videoLayout().find(r => r.clip.id === id);
  const worldLeft = $('timeline-world').getBoundingClientRect().left;
  drag = {
    mode: handle || mode, lane, id, el: document.querySelector(`.lane-block[data-id="${id}"]`), startX: e.clientX, worldLeft,
    grab: handle === 'left' ? 0 : (e.clientX - worldLeft) / zoom - (lane === 'video' ? row.at : item.at ?? 0),
    snapshot: JSON.stringify(project),
    origin: lane === 'video' ? videoLayout().findIndex(r => r.clip.id === id) : project.tracks[lane].findIndex(x => x.id === id),
    start: {...item}
  };
  lastDropIndex = lane === 'video' && drag.mode === 'move' ? drag.origin : null;
  window.addEventListener('pointermove', onDrag); window.addEventListener('pointerup', endDrag, {once: true});
  window.addEventListener('pointercancel', endDrag, {once: true});
}
function onDrag(e) {
  if (!drag) return;
  const item = findItem(drag.lane, drag.id); if (!item) return;
  const x = (e.clientX - drag.worldLeft) / zoom;
  const delta = (e.clientX - drag.startX) / zoom;
  if (drag.mode === 'left' || drag.mode === 'right') {
    if (drag.lane === 'video') {
      if (drag.mode === 'left') item.start = Math.min(Math.max(0, drag.start.start + delta), drag.start.end - MIN_CLIP);
      else item.end = Math.max(Math.min(drag.start.end + delta, item.duration), drag.start.start + MIN_CLIP);
      item.start = snap(item.start); item.end = snap(item.end);
    } else if (drag.lane === 'audio') {
      if (drag.mode === 'left') {
        const d = Math.max(delta, -drag.start.start, -drag.start.at);
        item.start = snap(drag.start.start + d); item.at = snap(drag.start.at + d);
      } else item.end = snap(Math.max(Math.min(drag.start.end + delta, item.duration), drag.start.start + MIN_CLIP));
    } else {
      if (drag.mode === 'left') item.at = snap(Math.max(0, drag.start.at + delta));
      else item.duration = snap(Math.max(MIN_CLIP, drag.start.duration + delta));
    }
    update();
  } else if (drag.lane !== 'video') {
    item.at = snap(Math.max(0, x - drag.grab));
    update();
  } else {
    lastDropIndex = videoDropIndex(x);
    const marker = dropMarker(), rows = videoLayout();
    const boundary = lastDropIndex < rows.length ? rows[lastDropIndex].at : movieDuration();
    marker.style.left = (boundary * zoom) + 'px';
  }
}
function dropMarker() { let m = $('timeline-world').querySelector('.drop-marker'); if (!m) { m = document.createElement('div'); m.className = 'drop-marker'; $('timeline-world').append(m); } return m; }
function videoDropIndex(x) {
  const rows = videoLayout(); let index = rows.length;
  for (let i = 0; i < rows.length; i++) { if (x < rows[i].at + rows[i].len / 2) { index = i; break; } }
  return index;
}
function endDrag() {
  window.removeEventListener('pointermove', onDrag);
  window.removeEventListener('pointercancel', endDrag);
  if (!drag) return;
  const d = drag; drag = null;
  document.querySelector('.drop-marker')?.remove();
  if (d.lane === 'video' && d.mode === 'move') {
    const from = videoLayout().findIndex(r => r.clip.id === d.id);
    const target = lastDropIndex == null ? from : lastDropIndex;
    if (target !== from) {
      commit(() => {
        const arr = project.tracks.video;
        const [moved] = arr.splice(from, 1);
        arr.splice(target > from ? target - 1 : target, 0, moved);
      });
    } else update();
  } else if (JSON.stringify(project) !== d.snapshot) {
    undoStack.push(d.snapshot); redoStack.length = 0; dirty = true; gestureKey = null; update();
  } else update();
  lastDropIndex = null;
}
let lastDropIndex = null;

/* pointerdown wiring */
$('timeline-world').addEventListener('pointerdown', e => {
  const block = e.target.closest('.lane-block');
  if (block) { startDrag(e, e.target.dataset.handle || 'move'); return; }
  if (e.target.id === 'playhead-handle') { startPlayheadDrag(e); return; }
  const lane = e.target.closest('.lane');
  if (lane || e.target.id === 'ruler') {
    const world = $('timeline-world').getBoundingClientRect();
    seek((e.clientX - world.left) / zoom);
    if (lane) { selection = null; update(); }
  }
});
let playheadDrag = false;
function startPlayheadDrag(e) { e.preventDefault(); playheadDrag = true; window.addEventListener('pointermove', playheadMove); window.addEventListener('pointerup', () => { playheadDrag = false; window.removeEventListener('pointermove', playheadMove); }, {once: true}); }
function playheadMove(e) { if (!playheadDrag) return; const world = $('timeline-world').getBoundingClientRect(); seek((e.clientX - world.left) / zoom); }

/* ---------- inspector events ---------- */
function withSelected(fn) { const item = selected(); if (item) commit(() => fn(item)); }
$('trim-start').addEventListener('change', () => withSelected(item => {
  const value = Number($('trim-start').value);
  if (!Number.isFinite(value) || value < 0 || value > item.end - MIN_CLIP) { notice('Start must be before the end of this clip.', true); renderInspector(); return; }
  item.start = snap(value);
}));
$('trim-end').addEventListener('change', () => withSelected(item => {
  const value = Number($('trim-end').value);
  if (!Number.isFinite(value) || value <= item.start + MIN_CLIP || value > item.duration) { notice('End must be after the start and within the source.', true); renderInspector(); return; }
  item.end = snap(value);
}));
$('clip-at').addEventListener('change', () => withSelected(item => { const v = Number($('clip-at').value); if (Number.isFinite(v) && v >= 0) item.at = snap(v); }));
$('set-start').onclick = () => withSelected(item => {
  const row = videoLayout().find(r => r.clip.id === item.id);
  const local = row ? time - row.at : time - item.at;
  item.start = snap(Math.min(Math.max(0, item.start + local), item.end - MIN_CLIP));
});
$('set-end').onclick = () => withSelected(item => {
  const row = videoLayout().find(r => r.clip.id === item.id);
  const local = row ? time - row.at : time - item.at;
  item.end = snap(Math.max(Math.min(item.start + local, item.duration), item.start + MIN_CLIP));
});
$('volume').addEventListener('input', () => { if (!selection) return; beginGesture('vol:' + selection.id); const item = selected(); if (!item) return; item.volume = Number($('volume').value) / 100; $('volume-value').textContent = $('volume').value + '%'; renderTimeline(); });
$('volume').addEventListener('change', endGesture);
$('mute').addEventListener('change', () => withSelected(item => { item.muted = $('mute').checked; if (selection.lane === 'video') { const audio = project.tracks.audio.find(a => a.videoId === item.id); if (audio) audio.muted = item.muted; } }));
$('move-left').onclick = () => withSelected(item => commit(() => { const arr = project.tracks.video; const i = arr.findIndex(x => x.id === item.id); if (i > 0) [arr[i - 1], arr[i]] = [arr[i], arr[i - 1]]; }));
$('move-right').onclick = () => withSelected(item => commit(() => { const arr = project.tracks.video; const i = arr.findIndex(x => x.id === item.id); if (i >= 0 && i < arr.length - 1) [arr[i + 1], arr[i]] = [arr[i], arr[i + 1]]; }));
$('detach-audio').onclick = () => withSelected(item => commit(() => {
  item.muted = true;
  project.tracks.audio.push({id: uid(), videoId: item.id, path: item.path, name: item.name, kind: 'audio', start: item.start, end: item.end, muted: false, volume: item.volume ?? 1, at: videoLayout().reduce((sum, r) => r.clip.id === item.id ? sum : sum + r.len, 0), duration: item.duration, hasAudio: true});
  notice('Video sound moved to its own Audio clip — drag it anywhere.');
}));
$('effect-type').addEventListener('change', () => withSelected(item => { item.type = $('effect-type').value; item.value = {brightness: 0.2, contrast: 1.2, grayscale: 1, sepia: 1}[item.type]; }));
$('effect-at').addEventListener('change', () => withSelected(item => { const v = Number($('effect-at').value); if (Number.isFinite(v) && v >= 0) item.at = snap(v); }));
$('effect-duration').addEventListener('change', () => withSelected(item => { const v = Number($('effect-duration').value); if (Number.isFinite(v) && v > 0) item.duration = snap(v); }));
$('effect-value').addEventListener('input', () => { if (!selection) return; beginGesture('effect:' + selection.id); const item = selected(); if (item) { item.value = Number($('effect-value').value); renderInspector(); renderEffectsFilter(); } });
$('effect-value').addEventListener('change', endGesture);

/* ---------- split / remove ---------- */
function splitSelection() {
  const item = selected(); if (!item) return;
  if (selection.lane === 'video') {
    const row = videoLayout().find(r => r.clip.id === item.id); if (!row || time <= row.at + MIN_CLIP || time >= row.at + row.len - MIN_CLIP) return;
    commit(() => {
      const local = item.start + (time - row.at);
      const second = {...item, id: uid(), start: snap(local), end: item.end};
      item.end = snap(local);
      project.tracks.video.splice(project.tracks.video.indexOf(item) + 1, 0, second);
      selection = {lane: 'video', id: second.id};
    });
    notice('Clip split — nothing was deleted.');
  } else if (selection.lane === 'audio') {
    const local = time - item.at;
    if (local <= MIN_CLIP || local >= item.end - item.start - MIN_CLIP) return;
    commit(() => {
      const second = {...item, id: uid(), start: snap(item.start + local), at: snap(item.at + local)};
      item.end = snap(item.start + local);
      project.tracks.audio.push(second);
      selection = {lane: 'audio', id: second.id};
    });
  }
}
$('split').onclick = splitSelection; $('split-selected').onclick = splitSelection;
$('remove').onclick = () => { const item = selected(); if (!item) return; commit(() => { project.tracks[selection.lane] = project.tracks[selection.lane].filter(x => x.id !== item.id); }); selection = null; update(); };

/* ---------- effect creation ---------- */
$('add-effect').onclick = () => {
  const type = $('effect-preset').value;
  const duration = movieDuration();
  const defaults = {brightness: 0.2, contrast: 1.2, grayscale: 1, sepia: 1};
  const item = {id: uid(), type, at: snap(Math.min(time, Math.max(0, duration - 1))), duration: snap(Math.max(MIN_CLIP, Math.min(2, duration || 2))), value: defaults[type]};
  commit(() => project.tracks.effects.push(item));
  select('effects', item.id);
  notice(`${type[0].toUpperCase() + type.slice(1)} added — drag its range, then adjust the amount on the right.`);
};

/* ---------- imports ---------- */
async function importFiles(files, target) {
  if (!files.length) return;
  importing = true; update();
  let added = 0; const failures = [];
  for (const file of files) {
    const audioOnly = target === 'audio' || (!file.type.startsWith('video') && file.type.startsWith('audio'));
    notice(`Importing ${file.name}… (${added + failures.length + 1}/${files.length})`);
    try {
      const clip = await api('/api/import?name=' + encodeURIComponent(file.name), file, true);
      clip.id = uid();
      if (audioOnly || clip.kind === 'audio') addToAudio(clip, movieDuration() ? time : 0);
      else addToVideo(clip);
      added++;
    } catch (error) { failures.push(`${file.name}: ${error.message}`); }
  }
  importing = false;
  notice(failures.length ? `${added} imported. ${failures.join(' ')}` : `${added} clip${added === 1 ? '' : 's'} added to your tracks.`, !!failures.length);
  update();
}
$('import-button').onclick = () => $('media-files').click();
$('empty-import').onclick = () => $('media-files').click();
$('audio-import').onclick = () => $('audio-files').click();
$('media-files').onchange = e => { importFiles([...e.target.files], 'auto'); e.target.value = ''; };
$('audio-files').onchange = e => { importFiles([...e.target.files], 'audio'); e.target.value = ''; };

/* drop files onto lanes */
['video-lane', 'audio-lane', 'effects-lane'].forEach(id => {
  const lane = $(id);
  lane.addEventListener('dragover', e => { if ([...e.dataTransfer.types].includes('Files') || [...e.dataTransfer.types].includes('text/classic-maker')) { e.preventDefault(); lane.classList.add('drop-target'); } });
  lane.addEventListener('dragleave', () => lane.classList.remove('drop-target'));
  lane.addEventListener('drop', e => {
    e.preventDefault(); lane.classList.remove('drop-target');
    const worldLeft = $('timeline-world').getBoundingClientRect().left;
    const at = Math.max(0, (e.clientX - worldLeft) / zoom);
    const payload = e.dataTransfer.getData('text/classic-maker');
    if (payload) {
      const info = JSON.parse(payload).source;
      if (!info) return;
      if (id === 'video-lane' && info.kind === 'video') addToVideo({...info});
      else if (id === 'audio-lane' && info.hasAudio) addToAudio({...info}, at);
      else notice(info.kind === 'video' ? 'Video belongs on the Video track.' : 'This source has no sound for the Audio track.', true);
      return;
    }
    importFiles([...e.dataTransfer.files], id === 'audio-lane' ? 'audio' : 'auto');
  });
});

/* ---------- save / open ---------- */
function serialize() { return {version: 2, name: project.name, tracks: project.tracks, output: project.output}; }
$('project-name').oninput = () => { project.name = $('project-name').value; dirty = true; };
$('save-button').onclick = () => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(serialize(), null, 2) + '\n'], {type: 'application/json'}));
  const a = document.createElement('a'); a.href = url;
  a.download = (project.name.trim().replace(/[^a-zA-Z0-9_-]+/g, '-') || 'my-movie') + '.classic-maker.json';
  a.click(); setTimeout(() => URL.revokeObjectURL(url), 30000);
  dirty = false; notice('Project downloaded. Source media stays in its original location.');
};
$('open-button').onclick = () => $('project-file').click();
$('project-file').onchange = async e => {
  const file = e.target.files[0]; e.target.value = ''; if (!file) return;
  if (dirty && !confirm('Open this project and replace your unsaved movie?')) return;
  try {
    const incoming = JSON.parse(await file.text());
    notice('Opening project and checking source media…');
    project = await api('/api/project', incoming);
    if (!project.tracks) project = {version: 2, name: project.name, tracks: {video: project.clips || [], audio: [], effects: []}, output: project.output};
    selection = null; dirty = false; time = 0; stop();
    $('project-name').value = project.name; $('resolution').value = project.output.resolution;
    undoStack.length = 0; redoStack.length = 0;
    update(); notice('Project opened. Audio and effect tracks are ready.');
  } catch (error) { notice('Could not open project: ' + error.message, true); }
};

/* ---------- export ---------- */
async function watchJob() {
  if (!jobId) return;
  try {
    const job = await api('/api/jobs/' + jobId);
    $('progress').value = job.progress;
    $('progress-label').textContent = job.status === 'running' ? `Rendering tracks ${Math.round(job.progress)}% · originals untouched` : $('progress-label').textContent;
    if (job.status === 'running') { setTimeout(watchJob, 600); return; }
    jobId = null; $('cancel-export').hidden = true; update();
    if (job.status === 'done') {
      $('progress-label').textContent = 'Your movie is ready.';
      $('download').href = job.download; $('download').download = (project.name || 'my-movie') + '.mp4'; $('download').hidden = false;
      notice('Movie exported. Click Download your movie to save your MP4.');
    } else notice(job.error || 'Export failed.', true);
  } catch (error) { $('progress-label').textContent = 'Connection lost. Reconnecting…'; notice(error.message + ' Keep the launcher running.', true); setTimeout(watchJob, 2000); }
}
$('export-button').onclick = async () => {
  stop(); $('export-button').disabled = true;
  try {
    const job = await api('/api/export', serialize()); jobId = job.id;
    $('export-progress').hidden = false; $('download').hidden = true; $('cancel-export').hidden = false; $('cancel-export').disabled = false; $('progress').value = 0;
    notice('FFmpeg is rendering your video, sound, and effect tracks.'); update(); watchJob();
  } catch (error) { notice(error.message, true); update(); }
};
$('cancel-export').onclick = async () => { if (!jobId) return; try { await api('/api/cancel', {id: jobId}); $('cancel-export').disabled = true; $('progress-label').textContent = 'Cancelling…'; } catch (error) { notice(error.message, true); } };

/* ---------- transport, zoom, keyboard ---------- */
$('jump-start').onclick = () => seek(0);
$('step-back').onclick = () => seek(time - 1 / 30, false);
$('step-forward').onclick = () => seek(time + 1 / 30, false);
$('play-movie').onclick = togglePlay;
$('seek-bar').oninput = e => seek(Number(e.target.value));
$('zoom').oninput = e => { zoom = Number(e.target.value); update(); };
$('fit-timeline').onclick = () => { const width = $('timeline-scroll').clientWidth - 50; zoom = Math.max(20, Math.min(180, Math.round(width / Math.max(1, movieDuration()) / 5) * 5)); $('zoom').value = zoom; update(); };
player.addEventListener('waiting', () => { if (playing) $('buffering').hidden = false; });
player.addEventListener('playing', () => { $('buffering').hidden = true; });
$('timeline-world').addEventListener('keydown', e => {
  if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); $('remove').click(); }
  if (e.key === 'ArrowLeft') { e.preventDefault(); seek(time - (e.shiftKey ? 1 : 1 / 30)); }
  if (e.key === 'ArrowRight') { e.preventDefault(); seek(time + (e.shiftKey ? 1 : 1 / 30)); }
  if (e.key === 'Home') { e.preventDefault(); seek(0); }
  if (e.key === 'End') { e.preventDefault(); seek(movieDuration(), false); }
});
document.addEventListener('keydown', e => {
  const typing = /^(INPUT|SELECT|TEXTAREA|BUTTON)$/.test(document.activeElement.tagName) || document.activeElement.isContentEditable;
  if (e.code === 'Space' && !typing) { e.preventDefault(); togglePlay(); }
  if ((e.key === 's' || e.key === 'S') && !typing && !e.ctrlKey && !e.metaKey) { e.preventDefault(); splitSelection(); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !typing) { e.preventDefault(); e.shiftKey ? redo() : undo(); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y' && !typing) { e.preventDefault(); redo(); }
});
$('resolution').onchange = () => { project.output.resolution = $('resolution').value; dirty = true; };
$('undo').onclick = undo; $('redo').onclick = redo;
$('about-button').onclick = () => $('about').showModal();

/* ---------- setup & init ---------- */
$('setup-button').onclick = async () => {
  $('setup-button').disabled = true; importing = true; update();
  notice('Downloading and verifying FFmpeg… keep this window open.');
  try { await api('/api/setup', {}); $('setup-area').hidden = true; notice('FFmpeg is ready. Import your first clips.'); }
  catch (error) { notice('Setup failed: ' + error.message, true); }
  finally { $('setup-button').disabled = false; importing = false; update(); }
};
window.addEventListener('beforeunload', e => { if (dirty || jobId || importing) { e.preventDefault(); e.returnValue = ''; } });
(async () => {
  update(); requestAnimationFrame(frame);
  try {
    const config = await api('/api/config');
    token = config.token; $('version').textContent = config.version;
    $('setup-area').hidden = config.ffmpegAvailable; update();
    notice(config.ffmpegAvailable ? 'Your editing room is ready. Import video, music, and voice to start.' : 'One last step: click Set up FFmpeg below — once only.', !config.ffmpegAvailable);
  } catch (error) { notice('Could not connect to Classic Maker. Keep the launcher running and reload. ' + error.message, true); }
})();
