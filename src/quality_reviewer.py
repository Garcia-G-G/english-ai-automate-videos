#!/usr/bin/env python3
"""
Quality Reviewer - Human-readable video quality analysis.

This analyzer acts like a real person reviewing your video,
providing plain-language feedback and actionable recommendations.

Unlike technical analyzers, this one:
- Explains what it's looking at in plain language
- Tells you WHY something is a problem
- Gives specific, actionable fixes
- Tracks your progress across iterations
- Provides context from previous reviews

Usage:
    python quality_reviewer.py --video output/video/test.mp4
    python quality_reviewer.py --video test.mp4 --history  # Include previous reviews
"""

import argparse
import json
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import hashlib

import cv2
import numpy as np

# History file for tracking iterations
HISTORY_DIR = Path(__file__).parent.parent / "output" / "reviews"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

# ============== QUALITY THRESHOLDS ==============

# Video basics
EXPECTED_WIDTH = 1080
EXPECTED_HEIGHT = 1920
MIN_FPS = 24
GOOD_FPS = 30
MIN_DURATION = 10       # seconds - very short
MAX_DURATION = 60       # seconds - too long for TikTok

# Audio
MIN_SAMPLE_RATE = 44100
CLIPPING_THRESHOLD_DB = -1.0     # max volume above this = clipping
QUIET_THRESHOLD_DB = -25         # mean volume below this = too quiet
GOOD_VOLUME_RANGE_DB = (-20, -10)  # comfortable listening range

# Speaking rate (words per minute)
MAX_SPEAKING_RATE_WPM = 200   # too fast
MIN_SPEAKING_RATE_WPM = 100   # too slow

# Countdown gaps (seconds)
COUNTDOWN_MIN_GAP = 0.8
COUNTDOWN_MAX_GAP = 1.3

# Visual thresholds
DARK_BRIGHTNESS = 80     # out of 255
BRIGHT_BRIGHTNESS = 200  # out of 255
FROZEN_THRESHOLD = 5     # avg pixel diff - below = mostly static
JARRING_THRESHOLD = 50   # avg pixel diff - above = dramatic changes


class QualityReviewer:
    """
    A human-like video quality reviewer.

    Provides feedback as if a real person watched your video
    and told you exactly what needs to improve.
    """

    def __init__(self, video_path: str, audio_json_path: str = None):
        self.video_path = Path(video_path)
        self.audio_json_path = audio_json_path

        # Auto-detect audio JSON if not provided
        if not self.audio_json_path:
            possible_json = self.video_path.with_suffix('.json')
            if possible_json.exists():
                self.audio_json_path = str(possible_json)

        self.findings = []  # List of (severity, category, message, fix)
        self.positive_notes = []  # Things that are good
        self.video_info = {}
        self.audio_data = None

        # Load history for this video
        self.history = self._load_history()

    def _get_video_hash(self) -> str:
        """Get a hash to identify this video across reviews."""
        # Use filename + size as identifier
        stat = self.video_path.stat()
        return hashlib.md5(f"{self.video_path.name}_{stat.st_size}".encode()).hexdigest()[:12]

    def _load_history(self) -> List[Dict]:
        """Load review history for this video."""
        history_file = HISTORY_DIR / f"{self.video_path.stem}_history.json"
        if history_file.exists():
            try:
                with open(history_file, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []

    def _save_history(self, review: Dict):
        """Save this review to history."""
        self.history.append(review)
        # Keep only last 10 reviews
        self.history = self.history[-10:]

        history_file = HISTORY_DIR / f"{self.video_path.stem}_history.json"
        with open(history_file, 'w') as f:
            json.dump(self.history, f, indent=2, default=str)

    def add_finding(self, severity: str, category: str, message: str, fix: str):
        """
        Add a finding.

        Args:
            severity: 'critical', 'warning', or 'suggestion'
            category: 'audio', 'visual', 'timing', 'language', 'content'
            message: Plain language description of the issue
            fix: Specific action to fix it
        """
        self.findings.append({
            'severity': severity,
            'category': category,
            'message': message,
            'fix': fix
        })

    def add_positive(self, message: str):
        """Note something that's working well."""
        self.positive_notes.append(message)

    def review(self) -> Dict:
        """
        Perform a complete review of the video.

        Returns a human-readable report.
        """
        print(f"\n{'='*70}")
        print("🎬 QUALITY REVIEW - Starting analysis...")
        print(f"{'='*70}")
        print(f"\nVideo: {self.video_path.name}")

        # Step 1: Basic video info
        print("\n📊 Step 1: Checking video basics...")
        self._check_video_basics()

        # Step 2: Audio quality
        print("🔊 Step 2: Analyzing audio quality...")
        self._check_audio_quality()

        # Step 3: Load and check word timestamps
        if self.audio_json_path and os.path.exists(self.audio_json_path):
            print("📝 Step 3: Checking word timing and language...")
            self._load_audio_data()
            self._check_word_timing()
            self._check_language_correctness()
        else:
            print("📝 Step 3: Skipped (no audio JSON found)")

        # Step 4: Visual analysis
        print("🎨 Step 4: Analyzing visual elements...")
        self._check_visual_quality()

        # Step 5: Content analysis (if script data available)
        if self.audio_data:
            print("📖 Step 5: Checking content structure...")
            self._check_content_structure()

        # Generate report
        return self._generate_report()

    def _check_video_basics(self):
        """Check basic video properties."""
        cap = cv2.VideoCapture(str(self.video_path))

        if not cap.isOpened():
            self.add_finding(
                'critical', 'video',
                "I couldn't open the video file. It might be corrupted or in an unsupported format.",
                "Try regenerating the video, or check if the file was fully written."
            )
            return

        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0

        cap.release()

        self.video_info = {
            'fps': fps,
            'width': width,
            'height': height,
            'duration': duration,
            'frame_count': frame_count
        }

        print(f"   Resolution: {width}x{height}")
        print(f"   Duration: {duration:.1f} seconds")
        print(f"   FPS: {fps:.0f}")

        # Check resolution
        if width != EXPECTED_WIDTH or height != EXPECTED_HEIGHT:
            if width == EXPECTED_HEIGHT and height == EXPECTED_WIDTH:
                self.add_finding(
                    'critical', 'video',
                    f"The video is in landscape format ({width}x{height}). TikTok/Reels need portrait format.",
                    f"Change VIDEO_WIDTH and VIDEO_HEIGHT in constants.py to {EXPECTED_WIDTH}x{EXPECTED_HEIGHT}."
                )
            else:
                self.add_finding(
                    'warning', 'video',
                    f"Resolution is {width}x{height}. Standard TikTok is {EXPECTED_WIDTH}x{EXPECTED_HEIGHT}.",
                    f"Consider using {EXPECTED_WIDTH}x{EXPECTED_HEIGHT} for optimal quality on TikTok/Reels."
                )
        else:
            self.add_positive(f"Resolution is perfect for TikTok/Reels ({EXPECTED_WIDTH}x{EXPECTED_HEIGHT})")

        # Check FPS
        if fps < MIN_FPS:
            self.add_finding(
                'warning', 'video',
                f"Frame rate is only {fps:.0f} FPS. Videos may look choppy.",
                f"Increase FPS to at least {MIN_FPS}, ideally {GOOD_FPS} for smooth playback."
            )
        elif fps >= GOOD_FPS:
            self.add_positive(f"Smooth frame rate ({fps:.0f} FPS)")

        # Check duration
        if duration < MIN_DURATION:
            self.add_finding(
                'warning', 'content',
                f"Video is very short ({duration:.0f}s). This might not engage viewers.",
                "Aim for at least 15-30 seconds for TikTok educational content."
            )
        elif duration > MAX_DURATION:
            self.add_finding(
                'suggestion', 'content',
                f"Video is {duration:.0f}s long. TikTok viewers prefer 15-45 second videos.",
                "Consider shortening the content or splitting into parts."
            )
        else:
            self.add_positive(f"Good video length ({duration:.0f}s) for TikTok engagement")

    def _check_audio_quality(self):
        """Check audio quality using ffprobe and ffmpeg."""
        try:
            # Get audio stream info
            cmd = [
                'ffprobe', '-v', 'error',
                '-select_streams', 'a:0',
                '-show_entries', 'stream=codec_name,sample_rate,channels,bit_rate',
                '-of', 'json',
                str(self.video_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                self.add_finding(
                    'critical', 'audio',
                    "No audio stream found in the video!",
                    "Check that TTS generation completed and audio was properly muxed."
                )
                return

            audio_info = json.loads(result.stdout)
            streams = audio_info.get('streams', [])

            if not streams:
                self.add_finding(
                    'critical', 'audio',
                    "Video has no audio track. Viewers won't hear anything!",
                    "Ensure the TTS step completed and the video generation included the audio."
                )
                return

            stream = streams[0]
            sample_rate = int(stream.get('sample_rate', 0))
            channels = int(stream.get('channels', 0))

            print(f"   Sample rate: {sample_rate} Hz")
            print(f"   Channels: {channels}")

            if sample_rate < MIN_SAMPLE_RATE:
                self.add_finding(
                    'warning', 'audio',
                    f"Audio sample rate is low ({sample_rate} Hz). This might sound muffled.",
                    "Use 44100 Hz sample rate for better audio quality."
                )
            else:
                self.add_positive("Audio quality is good (44.1kHz or higher)")

            # Analyze volume levels
            cmd_vol = [
                'ffmpeg', '-i', str(self.video_path),
                '-af', 'volumedetect',
                '-f', 'null', '-'
            ]
            result_vol = subprocess.run(cmd_vol, capture_output=True, text=True, timeout=60)

            max_vol = mean_vol = None
            for line in result_vol.stderr.split('\n'):
                if 'max_volume' in line:
                    try:
                        max_vol = float(line.split(':')[1].strip().replace(' dB', ''))
                    except:
                        pass
                if 'mean_volume' in line:
                    try:
                        mean_vol = float(line.split(':')[1].strip().replace(' dB', ''))
                    except:
                        pass

            if max_vol is not None:
                print(f"   Max volume: {max_vol:.1f} dB")
                if max_vol > CLIPPING_THRESHOLD_DB:
                    self.add_finding(
                        'warning', 'audio',
                        f"Audio might be clipping (max volume: {max_vol:.1f} dB). This can cause distortion.",
                        "Lower the TTS volume or add audio normalization."
                    )

            if mean_vol is not None:
                print(f"   Mean volume: {mean_vol:.1f} dB")
                if mean_vol < QUIET_THRESHOLD_DB:
                    self.add_finding(
                        'warning', 'audio',
                        f"Audio is quite quiet (mean: {mean_vol:.1f} dB). Viewers might not hear well.",
                        "Increase TTS volume or normalize audio to around -14 dB."
                    )
                elif GOOD_VOLUME_RANGE_DB[0] <= mean_vol <= GOOD_VOLUME_RANGE_DB[1]:
                    self.add_positive("Audio volume is at a good level")

        except subprocess.TimeoutExpired:
            self.add_finding(
                'warning', 'audio',
                "Audio analysis timed out. The video might be very long.",
                "This is usually fine - analysis just takes longer for long videos."
            )
        except Exception as e:
            self.add_finding(
                'warning', 'audio',
                f"Couldn't fully analyze audio: {str(e)}",
                "Make sure ffmpeg and ffprobe are installed."
            )

    def _load_audio_data(self):
        """Load audio timestamp data."""
        try:
            with open(self.audio_json_path, 'r', encoding='utf-8') as f:
                self.audio_data = json.load(f)
            print(f"   Loaded {len(self.audio_data.get('words', []))} word timestamps")
        except Exception as e:
            print(f"   Warning: Couldn't load audio data: {e}")

    def _check_word_timing(self):
        """Check word timing and pacing."""
        if not self.audio_data:
            return

        words = self.audio_data.get('words', [])
        duration = self.audio_data.get('duration', 0)

        if not words:
            self.add_finding(
                'warning', 'timing',
                "No word timestamps found in the audio data.",
                "This might mean Whisper couldn't transcribe the audio. Check TTS output."
            )
            return

        # Calculate speaking rate
        word_count = len(words)
        if duration > 0:
            words_per_second = word_count / duration
            words_per_minute = words_per_second * 60

            print(f"   Speaking rate: {words_per_minute:.0f} words/minute")

            if words_per_minute > MAX_SPEAKING_RATE_WPM:
                self.add_finding(
                    'warning', 'timing',
                    f"Speaking rate is too fast ({words_per_minute:.0f} words/min). Viewers can't follow.",
                    "Slow down the TTS speed (try 0.85-0.95x) or add more pauses."
                )
            elif words_per_minute < MIN_SPEAKING_RATE_WPM:
                self.add_finding(
                    'suggestion', 'timing',
                    f"Speaking rate is slow ({words_per_minute:.0f} words/min). Might lose attention.",
                    "Speed up slightly or trim unnecessary pauses."
                )
            else:
                self.add_positive(f"Speaking rate is comfortable ({words_per_minute:.0f} words/min)")

        # Check for countdown timing (quiz/true_false videos)
        video_type = self.audio_data.get('type', '')
        if video_type in ['quiz', 'true_false']:
            self._check_countdown_timing(words)

    def _check_countdown_timing(self, words: List[Dict]):
        """Check countdown timing for quiz videos."""
        # Find countdown words
        countdown_words = ['tres', 'dos', 'uno', '3', '2', '1']
        found = {}

        for i, word_info in enumerate(words):
            word = word_info.get('word', '').lower().strip('.,!?')
            if word in countdown_words:
                # Map to standard names
                key = {'tres': '3', '3': '3', 'dos': '2', '2': '2', 'uno': '1', '1': '1'}.get(word)
                if key and key not in found:
                    found[key] = word_info.get('start', 0)

        if len(found) < 3:
            self.add_finding(
                'warning', 'timing',
                "Couldn't find all countdown numbers (Tres, Dos, Uno).",
                "Make sure the script includes 'Tres... dos... uno...' for the countdown."
            )
            return

        # Check gaps
        gap_3_2 = found.get('2', 0) - found.get('3', 0)
        gap_2_1 = found.get('1', 0) - found.get('2', 0)

        print(f"   Countdown: 3→2 gap={gap_3_2:.2f}s, 2→1 gap={gap_2_1:.2f}s")

        if gap_3_2 < COUNTDOWN_MIN_GAP or gap_2_1 < COUNTDOWN_MIN_GAP:
            self.add_finding(
                'critical', 'timing',
                f"Countdown is too fast! Gaps are {gap_3_2:.2f}s and {gap_2_1:.2f}s (need ~1s each).",
                "Add ellipsis (...) after each number in the script: 'Tres... dos... uno...'"
            )
        elif COUNTDOWN_MIN_GAP <= gap_3_2 <= COUNTDOWN_MAX_GAP and COUNTDOWN_MIN_GAP <= gap_2_1 <= COUNTDOWN_MAX_GAP:
            self.add_positive("Countdown timing is good (about 1 second per number)")
        else:
            self.add_finding(
                'suggestion', 'timing',
                f"Countdown gaps are inconsistent ({gap_3_2:.2f}s and {gap_2_1:.2f}s).",
                "Try to make the gaps more even, around 1 second each."
            )

    def _check_language_correctness(self):
        """Check if words are correctly marked as English/Spanish."""
        if not self.audio_data:
            return

        words = self.audio_data.get('words', [])
        english_phrases = self.audio_data.get('english_phrases', [])

        # Build expected English word set
        expected_english = set()
        for phrase in english_phrases:
            for word in phrase.lower().split():
                expected_english.add(word.strip('.,!?\'\"'))

        # Spanish words that should NEVER be marked as English
        spanish_only = {
            'tres', 'dos', 'uno', 'opción', 'opciones', 'respuesta', 'correcta',
            'significa', 'cómo', 'dice', 'qué', 'verdadero', 'falso',
            'ahora', 'piensa', 'bien', 'escucha', 'ejemplo',
            'la', 'el', 'las', 'los', 'es', 'en', 'de', 'y', 'o', 'a',
        }

        wrong_english = []  # Spanish marked as English
        wrong_spanish = []  # English not marked

        for word_info in words:
            word = word_info.get('word', '').lower().strip('.,!?\'\"')
            is_marked_english = word_info.get('is_english', False)

            if word in spanish_only and is_marked_english:
                wrong_english.append(word_info.get('word', word))

            if word in expected_english and not is_marked_english:
                wrong_spanish.append(word_info.get('word', word))

        if wrong_english:
            self.add_finding(
                'critical', 'language',
                f"Spanish words incorrectly highlighted as English: {', '.join(wrong_english[:5])}",
                "Fix is_english_word() to only mark words from english_phrases, not common words."
            )

        if wrong_spanish:
            self.add_finding(
                'warning', 'language',
                f"Teaching words not highlighted: {', '.join(wrong_spanish[:5])}",
                "Make sure english_phrases in the script includes all teaching words."
            )

        if not wrong_english and not wrong_spanish:
            self.add_positive("Word language marking looks correct")

    def _check_visual_quality(self):
        """Check visual elements of the video."""
        cap = cv2.VideoCapture(str(self.video_path))

        if not cap.isOpened():
            return

        # Sample frames throughout the video
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)

        sample_times = [0.5, 2, 5, 10, 15]  # Sample at these seconds
        frames = []

        for t in sample_times:
            frame_idx = int(t * fps)
            if frame_idx < total_frames:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                if ret:
                    frames.append((t, frame))

        cap.release()

        if not frames:
            self.add_finding(
                'warning', 'visual',
                "Couldn't extract frames for visual analysis.",
                "The video might be too short or corrupted."
            )
            return

        # Analyze brightness and color
        brightness_values = []
        for t, frame in frames:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness_values.append(np.mean(gray))

        avg_brightness = np.mean(brightness_values)
        print(f"   Average brightness: {avg_brightness:.0f}/255")

        if avg_brightness < DARK_BRIGHTNESS:
            self.add_finding(
                'warning', 'visual',
                f"Video is quite dark (brightness: {avg_brightness:.0f}/255). Text might be hard to read.",
                "Use a brighter background or increase text brightness."
            )
        elif avg_brightness > BRIGHT_BRIGHTNESS:
            self.add_finding(
                'suggestion', 'visual',
                f"Video is very bright (brightness: {avg_brightness:.0f}/255). Might wash out on screens.",
                "Consider a slightly darker background for better contrast."
            )
        else:
            self.add_positive("Video brightness looks good")

        # Check for frozen frames (animation working?)
        if len(frames) >= 2:
            diffs = []
            for i in range(1, len(frames)):
                diff = np.mean(np.abs(frames[i][1].astype(float) - frames[i-1][1].astype(float)))
                diffs.append(diff)

            avg_diff = np.mean(diffs)
            if avg_diff < FROZEN_THRESHOLD:
                self.add_finding(
                    'critical', 'visual',
                    "The video appears mostly static - animations might not be working.",
                    "Check that create_frame_educational() is being called for each frame."
                )
            elif avg_diff > JARRING_THRESHOLD:
                self.add_finding(
                    'suggestion', 'visual',
                    "Visual changes are quite dramatic. Might be jarring to watch.",
                    "Consider smoother transitions between states."
                )
            else:
                self.add_positive("Animations appear to be working")

    def _check_content_structure(self):
        """Check the content structure of the video."""
        if not self.audio_data:
            return

        video_type = self.audio_data.get('type', 'educational')
        full_script = self.audio_data.get('full_script', '') or self.audio_data.get('text', '')

        print(f"   Video type: {video_type}")

        # Check for required elements based on type
        if video_type == 'quiz':
            self._check_quiz_structure()
        elif video_type == 'true_false':
            self._check_true_false_structure()
        elif video_type == 'educational':
            self._check_educational_structure()

    def _check_quiz_structure(self):
        """Check quiz video has all required elements."""
        question = self.audio_data.get('question', '')
        options = self.audio_data.get('options', {})
        correct = self.audio_data.get('correct', '')
        explanation = self.audio_data.get('explanation', '')

        if not question:
            self.add_finding('critical', 'content', "Quiz has no question!", "Add a 'question' field to the script.")

        if len(options) < 4:
            self.add_finding('critical', 'content', f"Quiz only has {len(options)} options. Need A, B, C, D.",
                           "Add all 4 options to the script.")

        # Check for duplicate options
        option_values = [v.lower().strip() for v in options.values()]
        if len(set(option_values)) < len(option_values):
            self.add_finding('critical', 'content', "Quiz has duplicate options! All options must be different.",
                           "Change the options to be 4 distinct answers.")
        else:
            self.add_positive("Quiz options are all different")

        if not correct or correct not in options:
            self.add_finding('critical', 'content', f"Invalid correct answer: '{correct}'",
                           "Set 'correct' to one of: A, B, C, or D")

        if not explanation:
            self.add_finding('warning', 'content', "Quiz has no explanation.",
                           "Add an 'explanation' to teach viewers why the answer is correct.")

    def _check_true_false_structure(self):
        """Check true/false video structure."""
        statement = self.audio_data.get('statement', '')
        correct = self.audio_data.get('correct')
        explanation = self.audio_data.get('explanation', '')

        if not statement:
            self.add_finding('critical', 'content', "True/False has no statement!",
                           "Add a 'statement' field to the script.")

        if correct is None:
            self.add_finding('critical', 'content', "No correct answer specified.",
                           "Set 'correct' to true or false.")

        if not explanation:
            self.add_finding('warning', 'content', "No explanation provided.",
                           "Add an 'explanation' to teach why it's true or false.")

    def _check_educational_structure(self):
        """Check educational video structure."""
        full_script = self.audio_data.get('full_script', '')
        english_phrases = self.audio_data.get('english_phrases', [])

        if not full_script:
            self.add_finding('critical', 'content', "No script text found!",
                           "Add 'full_script' to the data.")

        if not english_phrases:
            self.add_finding('warning', 'content', "No english_phrases defined.",
                           "Add 'english_phrases' to highlight teaching words.")
        else:
            self.add_positive(f"Teaching {len(english_phrases)} English phrases")

        # Check script has quotes around English phrases
        if full_script:
            quote_count = full_script.count("'")
            if quote_count < 2:
                self.add_finding('warning', 'content',
                               "Script doesn't seem to have English words in quotes.",
                               "Put English words in single quotes: 'embarrassed'")

    def _generate_report(self) -> Dict:
        """Generate the final human-readable report."""
        # Count issues by severity
        critical = [f for f in self.findings if f['severity'] == 'critical']
        warnings = [f for f in self.findings if f['severity'] == 'warning']
        suggestions = [f for f in self.findings if f['severity'] == 'suggestion']

        # Determine overall status
        if critical:
            status = 'FAIL'
            emoji = '❌'
        elif len(warnings) > 3:
            status = 'NEEDS WORK'
            emoji = '⚠️'
        elif warnings:
            status = 'OKAY'
            emoji = '🔶'
        else:
            status = 'PASS'
            emoji = '✅'

        # Build report
        report = {
            'status': status,
            'video': str(self.video_path),
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'critical_issues': len(critical),
                'warnings': len(warnings),
                'suggestions': len(suggestions),
                'positive_notes': len(self.positive_notes)
            },
            'findings': self.findings,
            'positive_notes': self.positive_notes,
            'video_info': self.video_info
        }

        # Print human-readable report
        print(f"\n{'='*70}")
        print(f"{emoji} REVIEW RESULT: {status}")
        print(f"{'='*70}")

        # Summary
        print(f"\nFound: {len(critical)} critical issues, {len(warnings)} warnings, {len(suggestions)} suggestions")

        # Critical issues first
        if critical:
            print(f"\n{'='*70}")
            print("🚨 CRITICAL ISSUES (Must Fix)")
            print(f"{'='*70}")
            for i, f in enumerate(critical, 1):
                print(f"\n{i}. [{f['category'].upper()}] {f['message']}")
                print(f"   👉 FIX: {f['fix']}")

        # Warnings
        if warnings:
            print(f"\n{'='*70}")
            print("⚠️ WARNINGS (Should Fix)")
            print(f"{'='*70}")
            for i, f in enumerate(warnings, 1):
                print(f"\n{i}. [{f['category'].upper()}] {f['message']}")
                print(f"   👉 FIX: {f['fix']}")

        # Suggestions
        if suggestions:
            print(f"\n{'='*70}")
            print("💡 SUGGESTIONS (Nice to Have)")
            print(f"{'='*70}")
            for i, f in enumerate(suggestions, 1):
                print(f"\n{i}. [{f['category'].upper()}] {f['message']}")
                print(f"   👉 FIX: {f['fix']}")

        # Positive notes
        if self.positive_notes:
            print(f"\n{'='*70}")
            print("✨ WHAT'S WORKING WELL")
            print(f"{'='*70}")
            for note in self.positive_notes:
                print(f"   ✓ {note}")

        # Compare with history
        if len(self.history) > 0:
            prev = self.history[-1]
            prev_critical = prev.get('summary', {}).get('critical_issues', 0)
            prev_warnings = prev.get('summary', {}).get('warnings', 0)

            print(f"\n{'='*70}")
            print("📈 PROGRESS FROM LAST REVIEW")
            print(f"{'='*70}")

            if len(critical) < prev_critical:
                print(f"   🎉 Fixed {prev_critical - len(critical)} critical issues!")
            elif len(critical) > prev_critical:
                print(f"   😟 {len(critical) - prev_critical} new critical issues appeared")
            else:
                print(f"   → Critical issues unchanged ({len(critical)})")

            if len(warnings) < prev_warnings:
                print(f"   🎉 Fixed {prev_warnings - len(warnings)} warnings!")
            elif len(warnings) > prev_warnings:
                print(f"   😟 {len(warnings) - prev_warnings} new warnings appeared")
            else:
                print(f"   → Warnings unchanged ({len(warnings)})")

        # Action items
        print(f"\n{'='*70}")
        print("📋 NEXT STEPS")
        print(f"{'='*70}")

        if status == 'FAIL':
            print("\n1. Fix all CRITICAL issues above")
            print("2. Regenerate the video")
            print("3. Run this reviewer again to verify fixes")
        elif status in ['NEEDS WORK', 'OKAY']:
            print("\n1. Address the warnings if possible")
            print("2. Consider the suggestions for polish")
            print("3. Video is usable but could be improved")
        else:
            print("\n✨ Video looks great! Ready to publish.")

        print(f"\n{'='*70}\n")

        # Save to history
        self._save_history(report)

        return report


def main():
    parser = argparse.ArgumentParser(
        description="Quality Reviewer - Human-readable video quality analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python quality_reviewer.py --video output/video/test.mp4
    python quality_reviewer.py --video test.mp4 --audio test.json
    python quality_reviewer.py --video test.mp4 --output report.json
        """
    )

    parser.add_argument("--video", "-v", required=True, help="Video file to review")
    parser.add_argument("--audio", "-a", help="Audio JSON file with timestamps")
    parser.add_argument("--output", "-o", help="Save report to JSON file")

    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(f"Error: Video not found: {args.video}")
        sys.exit(1)

    reviewer = QualityReviewer(args.video, args.audio)
    report = reviewer.review()

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        print(f"Report saved to: {args.output}")

    # Exit with appropriate code
    if report['status'] == 'FAIL':
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
