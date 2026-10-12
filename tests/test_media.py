"""Behavior regressions against real FFmpeg, not subprocess mocks."""
import array
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import unittest

from classic_maker.media import MakerError, ffmpeg_exe, probe, process_options, render, validate_project


def run(*arguments):
    return subprocess.run([ffmpeg_exe(), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', *arguments],
                          check=True, capture_output=True, **process_options()).stdout


class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='classic-maker-test-')
        cls.root = Path(cls.directory.name)
        cls.red = cls.root / 'red clip.mp4'
        cls.blue = cls.root / 'blue portrait.mp4'
        run('-f', 'lavfi', '-i', 'color=red:s=320x180:r=30:d=1', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(cls.red))
        run('-f', 'lavfi', '-i', 'color=blue:s=180x320:r=24:d=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(cls.blue))

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def project(self):
        return {'version': 2, 'name': 'A small movie', 'tracks': {'video': [
            {**probe(self.blue), 'start': 0.2, 'end': 0.6},
            {**probe(self.red), 'start': 0.2, 'end': 0.8}], 'audio': [], 'effects': []},
            'output': {'resolution': '720p', 'fps': 30}}

    def test_trim_reorder_and_silent_portrait_export(self):
        before = hashlib.sha256(self.red.read_bytes()).digest()
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            output = Path(temporary) / 'movie.mp4'
            render(self.project(), output)
            metadata = probe(output)
            self.assertAlmostEqual(metadata['duration'], 1.0, delta=0.09)
            self.assertTrue(metadata['hasAudio'])
            details = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(output)],
                                                capture_output=True, text=True, check=True, **process_options()).stdout) if __import__('shutil').which('ffprobe') else None
            if details:
                video = next(s for s in details['streams'] if s['codec_type'] == 'video')
                self.assertEqual((video['width'], video['height']), (1280, 720))
                self.assertEqual(video['avg_frame_rate'], '30/1')
            blue = run('-ss', '0.15', '-i', str(output), '-frames:v', '1', '-vf', 'crop=2:2:iw/2:ih/2,scale=1:1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1')
            red = run('-ss', '0.75', '-i', str(output), '-frames:v', '1', '-vf', 'crop=2:2:iw/2:ih/2,scale=1:1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1')
            self.assertGreater(blue[2], 200)
            self.assertLess(blue[0], 30)
            self.assertGreater(red[0], 200)
            samples = array.array('h', run('-i', str(output), '-vn', '-ac', '1', '-ar', '48000', '-f', 's16le', 'pipe:1'))
            def rms(a, b):
                window = samples[int(a * 48000):int(b * 48000)]
                return math.sqrt(sum(v * v for v in window) / len(window))
            self.assertLess(rms(0.1, 0.25), 5)
            self.assertGreater(rms(0.65, 0.85), 500)
        self.assertEqual(hashlib.sha256(self.red.read_bytes()).digest(), before)

    def test_join_preserves_even_video_frame_spacing(self):
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            source = Path(temporary) / 'four seconds.mp4'
            run('-f', 'lavfi', '-i', 'color=red:s=320x180:r=30:d=4',
                '-f', 'lavfi', '-i', 'sine=frequency=440:duration=4',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(source))
            project = self.project()
            project['tracks']['video'] = [probe(source), probe(self.blue)]
            output = Path(temporary) / 'joined.mp4'
            render(project, output)
            inspection = subprocess.run([ffmpeg_exe(), '-hide_banner', '-loglevel', 'info', '-i', str(output),
                                         '-vf', 'showinfo', '-an', '-f', 'null', '-'],
                                        capture_output=True, text=True, check=True, **process_options())
            timestamps = [float(value) for value in re.findall(r'pts_time:([0-9.]+)', inspection.stderr)]
            # AAC packet tails used to leave timestamp gaps at the cut.
            self.assertAlmostEqual(timestamps[-1] - timestamps[0], (len(timestamps) - 1) / 30, delta=0.0001)
            for first, second in zip(timestamps, timestamps[1:]):
                self.assertAlmostEqual(second - first, 1 / 30, delta=0.0001)

    def test_mute_removes_source_audio(self):
        project = self.project()
        project['tracks']['video'] = [project['tracks']['video'][1]]
        project['tracks']['video'][0]['muted'] = True
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            output = Path(temporary) / 'muted.mp4'
            render(project, output)
            samples = array.array('h', run('-i', str(output), '-vn', '-ac', '1', '-f', 's16le', 'pipe:1'))
            self.assertLess(max(abs(n) for n in samples), 5)

    def test_rejects_invalid_trim_boundaries(self):
        for start, end in [(-1, 0.5), (0.5, 0.5), (0.6, 0.2), (0, 2), (float('nan'), 1), (0, float('inf')), (False, 1)]:
            with self.subTest(start=start, end=end):
                project = self.project()
                project['tracks']['video'][0].update(start=start, end=end)
                with self.assertRaises(MakerError):
                    validate_project(project)

    def test_relative_paths_are_resolved_against_project_directory(self):
        project = self.project()
        project['tracks']['video'][0]['path'] = self.blue.name
        normalized = validate_project(project, self.root)
        self.assertEqual(normalized['tracks']['video'][0]['path'], str(self.blue.resolve()))

    def test_v1_project_migrates_to_v2_tracks(self):
        v1 = {'version': 1, 'name': 'Old', 'clips': [{**probe(self.red), 'start': 0, 'end': 0.5}],
              'output': {'resolution': '720p', 'fps': 30}}
        migrated = validate_project(v1)
        self.assertEqual(migrated['version'], 2)
        self.assertEqual(len(migrated['tracks']['video']), 1)
        self.assertEqual(migrated['tracks']['audio'], [])
        self.assertEqual(migrated['tracks']['effects'], [])
        self.assertNotIn('clips', migrated)

    def test_audio_only_media_probes_as_audio(self):
        mp3 = self.root / 'sound.mp3'
        run('-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', '-c:a', 'libmp3lame', str(mp3))
        info = probe(mp3)
        self.assertEqual(info['kind'], 'audio')
        self.assertTrue(info['hasAudio'])

    def test_audio_track_validates_placement_volume_and_video_lane_rules(self):
        mp3 = self.root / 'voice.mp3'
        if not mp3.exists():
            run('-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', '-c:a', 'libmp3lame', str(mp3))
        project = self.project()
        project['tracks']['audio'] = [{'path': str(mp3), 'at': 0.5, 'volume': 0.4, 'start': 0.1, 'end': 1.5}]
        validated = validate_project(project)
        clip = validated['tracks']['audio'][0]
        self.assertEqual((clip['at'], clip['volume'], clip['start'], clip['end']), (0.5, 0.4, 0.1, 1.5))
        for bad in [{'volume': 1.5}, {'volume': -0.1}, {'at': -1}, {'start': 1.9, 'end': 0.2}]:
            broken = self.project()
            broken['tracks']['audio'] = [{**project['tracks']['audio'][0], **bad}]
            with self.subTest(bad=bad), self.assertRaises(MakerError):
                validate_project(broken)
        wrong_lane = self.project()
        wrong_lane['tracks']['video'] = [{**wrong_lane['tracks']['video'][0], 'path': str(mp3)}]
        with self.assertRaises(MakerError):
            validate_project(wrong_lane)

    def test_independent_audio_renders_at_placement_with_gain(self):
        mp3 = self.root / 'mix.mp3'
        if not mp3.exists():
            run('-f', 'lavfi', '-i', 'sine=frequency=880:duration=2', '-c:a', 'libmp3lame', str(mp3))
        project = self.project()
        project['tracks']['video'] = [{**probe(self.red), 'start': 0, 'end': 1, 'muted': True}]
        project['tracks']['audio'] = [{'path': str(mp3), 'at': 0.5, 'volume': 1, 'start': 0, 'end': 1}]
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            output = Path(temporary) / 'mixed.mp4'
            render(project, output)
            samples = array.array('h', run('-i', str(output), '-vn', '-ac', '1', '-ar', '48000', '-f', 's16le', 'pipe:1'))
            def rms(a, b):
                window = samples[int(a * 48000):int(b * 48000)]
                return math.sqrt(sum(v * v for v in window) / len(window))
            self.assertGreater(rms(0.55, 0.95), 300)   # independent audio present after placement
            self.assertLess(rms(0.05, 0.35), 50)       # silent before its placement
            self.assertAlmostEqual(probe(output)['duration'], 1.0, delta=0.12)

    def test_timed_effect_changes_only_its_range(self):
        project = self.project()
        project['tracks']['video'] = [{**probe(self.blue), 'start': 0, 'end': 1}]
        project['tracks']['effects'] = [{'id': 'gray', 'type': 'grayscale', 'at': 0.4, 'duration': 0.3, 'value': 1}]
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            output = Path(temporary) / 'effected.mp4'
            render(project, output)
            def color(at):
                raw = run('-ss', str(at), '-i', str(output), '-frames:v', '1',
                          '-vf', 'crop=2:2:iw/2:ih/2,scale=1:1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1')
                return raw[0], raw[1], raw[2]
            before, during, after = color(0.15), color(0.55), color(0.85)
            def spread(pixel): return max(pixel) - min(pixel)
            self.assertGreater(spread(before), 40)      # blue still colorful
            self.assertLess(spread(during), 12)         # grayscale only inside range
            self.assertGreater(spread(after), 40)       # restored after range

    def test_original_is_never_an_export_destination(self):
        with self.assertRaisesRegex(MakerError, 'Source clips are never overwritten'):
            render(self.project(), self.red, overwrite=True)

    def test_existing_output_requires_explicit_overwrite(self):
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            output = Path(temporary) / 'existing.mp4'
            output.write_bytes(b'keep this file')
            with self.assertRaisesRegex(MakerError, 'already exists'):
                render(self.project(), output)
            self.assertEqual(output.read_bytes(), b'keep this file')

    def test_cancel_preserves_destination_and_removes_working_files(self):
        cancel = threading.Event()
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            output = Path(temporary) / 'cancelled.mp4'
            output.write_bytes(b'previous movie')
            def on_progress(value):
                cancel.set()
            with self.assertRaisesRegex(MakerError, 'cancelled'):
                render(self.project(), output, overwrite=True, cancel=cancel, progress=on_progress)
            self.assertEqual(output.read_bytes(), b'previous movie')
            self.assertEqual(list(Path(temporary).iterdir()), [output])


if __name__ == '__main__':
    unittest.main()
