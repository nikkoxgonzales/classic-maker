'use strict';
const $ = id => document.getElementById(id);
let project = {version: 1, name: 'My first movie', clips: [], output: {resolution: '720p', fps: 30}};
let token = '', selected = -1, dirty = false, importing = false, jobId = null, movieMode = false, loadingPreview = false;
const player = $('player');
const current = () => project.clips[selected];
const time = seconds => { const n = Math.max(0, Math.round(seconds)); return `${String(Math.floor(n / 60)).padStart(2, '0')}:${String(n % 60).padStart(2, '0')}`; };
function notice(text, error = false) { $('notice').textContent = text; $('notice').classList.toggle('error', error); }
async function api(path, body, raw = false) {
  const options = body === undefined ? {} : {method: 'POST', headers: {'X-Classic-Maker-Token': token}, body: raw ? body : JSON.stringify(body)};
  if (body !== undefined && !raw) options.headers['Content-Type'] = 'application/json';
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
  return data;
}
function changed() { dirty = true; update(); }
function update() {
  $('clip-count').textContent = project.clips.length;
  $('library-empty').hidden = project.clips.length > 0;
  $('preview-empty').hidden = selected >= 0;
  $('trim-empty').hidden = selected >= 0;
  $('trim-controls').disabled = selected < 0;
  $('play-movie').disabled = project.clips.length === 0 || importing;
  $('export-button').disabled = project.clips.length === 0 || importing || !!jobId || !token;
  $('save-button').disabled = importing || !token;
  $('open-button').disabled = importing || !token;
  $('import-button').disabled = importing || !token;
  $('empty-import').disabled = importing || !token;
  $('play-movie').textContent = movieMode ? '■ Stop movie' : '▶ Play movie';
  $('total-duration').textContent = time(project.clips.reduce((sum, c) => sum + c.end - c.start, 0));
  $('clip-list').replaceChildren(); $('storyboard').replaceChildren();
  project.clips.forEach((clip, index) => {
    const button = document.createElement('button');
    button.className = 'clip-button' + (index === selected ? ' selected' : '');
    button.setAttribute('aria-pressed', String(index === selected));
    button.title = clip.name;
    const number = document.createElement('span'); number.className = 'clip-number'; number.textContent = String(index + 1).padStart(2, '0');
    const meta = document.createElement('span'); meta.className = 'clip-meta';
    const name = document.createElement('strong'); name.textContent = clip.name;
    const length = document.createElement('small'); length.textContent = `${time(clip.end - clip.start)} · ${clip.muted ? 'muted' : clip.hasAudio ? 'original audio' : 'no audio'}`;
    meta.append(name, length); button.append(number, meta);
    button.onclick = () => selectClip(index);
    $('clip-list').append(button);
    const card = document.createElement('button'); card.className = 'story-card' + (index === selected ? ' selected' : '');
    card.setAttribute('aria-label', `Clip ${index + 1}: ${clip.name}`); card.setAttribute('aria-pressed', String(index === selected));
    const top = document.createElement('span'); top.className = 'scene-top';
    const seq = document.createElement('span'); seq.textContent = `CLIP ${String(index + 1).padStart(2, '0')}`;
    const sound = document.createElement('span'); sound.textContent = clip.muted ? 'MUTED' : '▤'; top.append(seq, sound);
    const cardName = document.createElement('strong'); cardName.textContent = clip.name;
    const range = document.createElement('small'); range.textContent = `${time(clip.start)} → ${time(clip.end)}`;
    card.append(top, cardName, range); card.onclick = () => selectClip(index); $('storyboard').append(card);
  });
  if (!project.clips.length) { const text = document.createElement('p'); text.className = 'subtle'; text.textContent = 'Your story starts here. Import your first clip.'; $('storyboard').append(text); }
  if (current()) {
    const clip = current();
    $('selected-name').textContent = clip.name; $('preview-label').textContent = clip.name;
    $('trim-start').value = clip.start.toFixed(2); $('trim-end').value = clip.end.toFixed(2);
    $('trim-start').max = clip.duration; $('trim-end').max = clip.duration;
    $('trim-duration').textContent = `${(clip.end - clip.start).toFixed(2)}s kept of ${clip.duration.toFixed(2)}s`;
    $('mute').checked = clip.muted; player.muted = clip.muted;
    $('move-left').disabled = selected === 0; $('move-right').disabled = selected === project.clips.length - 1;
  } else { $('preview-label').textContent = 'No clip selected'; }
}
function selectClip(index, autoplay = false, keepMovie = false) {
  if (!keepMovie) movieMode = false;
  player.pause(); selected = index; loadingPreview = true;
  if (!current()) { player.removeAttribute('src'); player.load(); loadingPreview = false; update(); return; }
  const clip = current(); player.muted = clip.muted;
  player.src = '/api/media?path=' + encodeURIComponent(clip.path);
  player.onloadedmetadata = () => {
    loadingPreview = false; player.currentTime = clip.start;
    if (autoplay) player.play().catch(() => { movieMode = false; update(); notice('Press play in the preview to start playback.'); });
  };
  player.load(); update();
}
function nextClip() {
  if (loadingPreview || !current()) return;
  if (movieMode && selected < project.clips.length - 1) selectClip(selected + 1, true, true);
  else { player.pause(); movieMode = false; $('play-state').textContent = 'Preview complete.'; update(); }
}
player.addEventListener('timeupdate', () => {
  if (loadingPreview || !current()) return;
  if (!player.paused && player.currentTime >= current().end - 0.015) nextClip();
  else if (player.currentTime < current().start - 0.05) player.currentTime = current().start;
});
player.addEventListener('ended', nextClip);
player.addEventListener('play', () => { if (current() && (player.currentTime >= current().end - 0.02 || player.currentTime < current().start)) player.currentTime = current().start; });
player.addEventListener('error', () => { loadingPreview = false; movieMode = false; update(); notice('This browser cannot preview this codec. The clip can still be trimmed by seconds and exported by FFmpeg. MP4 with H.264 works best for preview.', true); });
$('play-movie').onclick = () => {
  if (movieMode) { movieMode = false; player.pause(); $('play-state').textContent = 'Preview stopped.'; update(); }
  else if (project.clips.length) { movieMode = true; $('play-state').textContent = 'Playing your movie in order…'; selectClip(0, true, true); }
};
function trim(start, end) {
  const clip = current(); if (!clip) return;
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start || end > clip.duration + 0.025) {
    notice(`Use a start before the end, between 0 and ${clip.duration.toFixed(2)} seconds.`, true); update(); return;
  }
  movieMode = false; player.pause(); clip.start = start; clip.end = Math.min(end, clip.duration);
  if (player.currentTime < clip.start || player.currentTime >= clip.end) player.currentTime = clip.start;
  changed(); notice('Trim saved in your movie. Your original clip is unchanged.');
}
$('trim-start').onchange = () => trim($('trim-start').valueAsNumber, $('trim-end').valueAsNumber);
$('trim-end').onchange = () => trim($('trim-start').valueAsNumber, $('trim-end').valueAsNumber);
$('set-start').onclick = () => { if (current()) trim(Math.round(player.currentTime * 100) / 100, current().end); };
$('set-end').onclick = () => { if (current()) trim(current().start, Math.round(player.currentTime * 100) / 100); };
$('mute').onchange = () => { if (current()) { current().muted = $('mute').checked; changed(); } };
function move(delta) { const next = selected + delta; if (!current() || next < 0 || next >= project.clips.length) return; movieMode = false; player.pause(); [project.clips[selected], project.clips[next]] = [project.clips[next], project.clips[selected]]; selected = next; changed(); }
$('move-left').onclick = () => move(-1); $('move-right').onclick = () => move(1);
$('remove').onclick = () => { if (!current()) return; project.clips.splice(selected, 1); selectClip(Math.min(selected, project.clips.length - 1)); changed(); notice('Removed from your movie. The source file is still on your computer.'); };
$('project-name').oninput = () => { project.name = $('project-name').value; dirty = true; };
$('resolution').onchange = () => { project.output.resolution = $('resolution').value; dirty = true; };
function importPicker() { $('media-files').click(); }
$('import-button').onclick = importPicker; $('empty-import').onclick = importPicker;
$('media-files').onchange = async () => {
  const files = Array.from($('media-files').files); if (!files.length) return;
  importing = true; movieMode = false; player.pause(); update(); let added = 0, failures = [];
  for (const file of files) {
    notice(`Importing ${file.name}… (${added + failures.length + 1}/${files.length})`);
    try { const clip = await api('/api/import?name=' + encodeURIComponent(file.name), file, true); project.clips.push(clip); added++; dirty = true; }
    catch (error) { failures.push(`${file.name}: ${error.message}`); }
  }
  importing = false; $('media-files').value = ''; selectClip(project.clips.length ? project.clips.length - 1 : -1);
  notice(failures.length ? `${added} imported. ${failures.join(' ')}` : `${added} clip${added === 1 ? '' : 's'} imported. Select a clip, trim the good parts, and arrange your story.`, !!failures.length);
};
$('open-button').onclick = () => $('project-file').click();
$('project-file').onchange = async () => {
  const file = $('project-file').files[0]; if (!file) return;
  if (dirty && !confirm('Open this project and replace your unsaved movie? Save your project first if you want to keep it.')) { $('project-file').value = ''; return; }
  try {
    const incoming = JSON.parse(await file.text()); notice('Opening project and checking source clips…');
    const loaded = await api('/api/project', incoming); project = loaded; dirty = false;
    $('project-name').value = project.name; $('resolution').value = project.output.resolution; selectClip(project.clips.length ? 0 : -1);
    notice('Project opened. Source files must stay in the same location; projects do not contain the videos themselves.');
  } catch (error) { notice('Could not open project: ' + error.message, true); }
  $('project-file').value = '';
};
$('save-button').onclick = () => {
  const payload = {version: 1, name: project.name, clips: project.clips.map(({id, path, name, start, end, muted}) => ({id, path, name, start, end, muted})), output: project.output};
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2) + '\n'], {type: 'application/json'}));
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = (project.name.trim().replace(/[^a-zA-Z0-9_-]+/g, '-') || 'my-movie') + '.classic-maker.json'; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000); dirty = false;
  notice('Project downloaded. Keep the source files too; use Export movie for a shareable MP4.');
};
async function watchJob() {
  if (!jobId) return;
  try {
    const job = await api('/api/jobs/' + jobId);
    $('progress').value = job.progress; $('progress-label').textContent = `Exporting ${Math.round(job.progress)}% · originals untouched`;
    if (job.status === 'running') { setTimeout(watchJob, 600); return; }
    jobId = null; $('cancel-export').hidden = true; update();
    if (job.status === 'done') { $('progress-label').textContent = 'Your movie is ready.'; $('download').href = job.download; $('download').download = (project.name || 'my-movie') + '.mp4'; $('download').hidden = false; notice('Movie exported. Click Download your movie to save your MP4.'); }
    else notice(job.error || 'Export failed.', true);
  } catch (error) { $('progress-label').textContent = 'Connection lost. Reconnecting…'; notice('Could not check export: ' + error.message + ' Keep the launcher running.', true); setTimeout(watchJob, 2000); }
}
$('export-button').onclick = async () => {
  movieMode = false; player.pause(); $('export-button').disabled = true;
  try {
    const job = await api('/api/export', project); jobId = job.id;
    $('export-progress').hidden = false; $('download').hidden = true; $('cancel-export').hidden = false; $('cancel-export').disabled = false; $('progress').value = 0;
    notice('FFmpeg is making your movie. You can keep editing; this export uses the current snapshot.'); update(); watchJob();
  } catch (error) { notice(error.message, true); update(); }
};
$('cancel-export').onclick = async () => { if (!jobId) return; try { await api('/api/cancel', {id: jobId}); $('cancel-export').disabled = true; $('progress-label').textContent = 'Cancelling…'; } catch (error) { notice(error.message, true); } };
$('about-button').onclick = () => $('about').showModal();
$('setup-button').onclick = async () => {
  $('setup-button').disabled = true; importing = true; update();
  notice('Downloading and verifying FFmpeg… keep this window open. This may take a minute.');
  try { await api('/api/setup', {}); $('setup-area').hidden = true; notice('FFmpeg is ready. Import your first clips — no more setup needed.'); }
  catch (error) { notice('Setup failed: ' + error.message + ' You can also install FFmpeg with your system package manager.', true); }
  finally { $('setup-button').disabled = false; importing = false; update(); }
};
window.addEventListener('beforeunload', event => { if (dirty || jobId || importing) { event.preventDefault(); event.returnValue = ''; } });
(async () => {
  update();
  try { const config = await api('/api/config'); token = config.token; $('version').textContent = config.version; $('setup-area').hidden = config.ffmpegAvailable; update(); notice(config.ffmpegAvailable ? 'Your editing room is ready. Import a few clips to start — everything stays on this computer.' : 'One last step: click Set up FFmpeg below. You only need to do this once.', !config.ffmpegAvailable); }
  catch (error) { notice('Could not connect to Classic Maker. Keep the launcher running and reload this page. ' + error.message, true); }
})();
