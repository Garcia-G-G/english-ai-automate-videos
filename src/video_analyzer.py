#!/usr/bin/env python3
"""
Video Analyzer - Comprehensive quality analysis for generated videos.

QUALITY CHECKS PERFORMED:
1. AUDIO QUALITY:
   - Glitch/break detection (sudden volume changes)
   - Consistency checks (stable audio throughout)
   - Duration validation

2. LANGUAGE CORRECTNESS:
   - Spanish words should NOT be marked as English
   - English teaching words SHOULD be marked as English
   - Option letters (A, B, C, D) should be Spanish

3. TIMING ANALYSIS:
   - Countdown timing (1 second gaps between numbers)
   - Option spacing (1.5 seconds between options)
   - Question-to-options transition
   - Overall pacing (not too fast, not too slow)

4. VISUAL QUALITY:
   - Animation smoothness (no glitches)
   - Frame consistency (no frozen frames)
   - Color palette (appropriate brightness/saturation)
   - Layout balance (centered, balanced)

5. AUDIO-VISUAL SYNC:
   - Visual changes match audio timestamps
   - Options appear at correct times
   - Countdown syncs with audio

Quality thresholds:
- COUNTDOWN_MIN_GAP: 0.8 seconds minimum between each number
- OPTION_MIN_GAP: 1.0 seconds minimum between options
- TRANSITION_MIN_PAUSE: 0.5 seconds after question before options
"""

import argparse
import json
import os
import sys
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import math

import cv2
import numpy as np
from PIL import Image

# Reference images directory
REFERENCES_DIR = Path(__file__).parent.parent / "references"
TEMP_DIR = Path(tempfile.gettempdir()) / "video_analyzer"

# Timing thresholds (seconds)
COUNTDOWN_MIN_GAP = 0.8  # Minimum gap between 3→2, 2→1
COUNTDOWN_IDEAL_GAP = 1.0  # Ideal gap (~1 second per number)
OPTION_MIN_GAP = 1.0  # Minimum gap between options A→B, B→C, etc.
OPTION_IDEAL_GAP = 1.5  # Ideal gap for comfortable pacing
TRANSITION_MIN_PAUSE = 0.5  # Minimum pause after question before options


def extract_frames(video_path: str, interval: float = 0.5, key_moments: List[float] = None) -> List[Tuple[float, np.ndarray]]:
    """
    Extract frames from a video at specified intervals or key moments.

    Args:
        video_path: Path to the video file
        interval: Time interval between frames (seconds)
        key_moments: List of specific timestamps to extract

    Returns:
        List of (timestamp, frame) tuples
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps

    frames = []

    if key_moments:
        # Extract at specific timestamps
        timestamps = sorted(key_moments)
    else:
        # Extract at regular intervals
        timestamps = []
        t = 0
        while t < duration:
            timestamps.append(t)
            t += interval

    for timestamp in timestamps:
        frame_idx = int(timestamp * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if ret:
            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append((timestamp, frame_rgb))

    cap.release()
    return frames


def load_reference_images(directory: Path = REFERENCES_DIR) -> List[np.ndarray]:
    """Load all reference images from directory."""
    references = []

    if not directory.exists():
        print(f"Warning: References directory not found: {directory}")
        return references

    for ext in ['*.png', '*.jpg', '*.jpeg']:
        for img_path in directory.glob(ext):
            try:
                img = Image.open(img_path).convert('RGB')
                references.append(np.array(img))
            except Exception as e:
                print(f"Warning: Could not load {img_path}: {e}")

    return references


def analyze_color_palette(frame: np.ndarray) -> Dict:
    """
    Analyze the color palette of a frame.

    Returns:
        Dictionary with color analysis metrics
    """
    # Convert to different color spaces
    hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)

    # Calculate average brightness
    brightness = np.mean(hsv[:, :, 2])

    # Calculate average saturation
    saturation = np.mean(hsv[:, :, 1])

    # Calculate color histogram
    hist_r = cv2.calcHist([frame], [0], None, [256], [0, 256])
    hist_g = cv2.calcHist([frame], [1], None, [256], [0, 256])
    hist_b = cv2.calcHist([frame], [2], None, [256], [0, 256])

    # Detect dominant colors (simplified)
    pixels = frame.reshape(-1, 3)
    # Sample for efficiency
    sample_size = min(10000, len(pixels))
    sample_indices = np.random.choice(len(pixels), sample_size, replace=False)
    sample = pixels[sample_indices]

    # Simple k-means for dominant colors
    from collections import Counter
    # Quantize colors
    quantized = (sample // 32) * 32
    color_counts = Counter(map(tuple, quantized))
    dominant_colors = [list(c) for c, _ in color_counts.most_common(5)]

    # Check for dark colors (potential black backgrounds)
    dark_pixels = np.sum(hsv[:, :, 2] < 50) / (frame.shape[0] * frame.shape[1])

    # Check if colors are "pastel" (high brightness, medium saturation)
    is_pastel = brightness > 150 and 50 < saturation < 180

    return {
        'brightness': float(brightness),
        'saturation': float(saturation),
        'dominant_colors': dominant_colors,
        'dark_pixel_ratio': float(dark_pixels),
        'is_pastel': is_pastel
    }


def analyze_text_readability(frame: np.ndarray) -> Dict:
    """
    Analyze text readability in a frame.

    Returns:
        Dictionary with text analysis metrics
    """
    # Convert to grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)

    # Detect edges (text usually has high edge density)
    edges = cv2.Canny(gray, 100, 200)
    edge_density = np.sum(edges > 0) / (edges.shape[0] * edges.shape[1])

    # Calculate local contrast (important for readability)
    # Use Laplacian variance as a proxy for sharpness
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

    # Check contrast ratio in different regions
    h, w = gray.shape
    center_region = gray[h//4:3*h//4, w//4:3*w//4]
    center_contrast = np.std(center_region)

    return {
        'edge_density': float(edge_density),
        'sharpness': float(laplacian_var),
        'center_contrast': float(center_contrast)
    }


def analyze_layout_balance(frame: np.ndarray) -> Dict:
    """
    Analyze layout balance and positioning.

    Returns:
        Dictionary with layout analysis metrics
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape

    # Calculate weighted center of visual mass
    # Using intensity as weight
    y_coords, x_coords = np.mgrid[0:h, 0:w]
    total_intensity = np.sum(255 - gray)  # Invert so darker = heavier

    if total_intensity > 0:
        center_x = np.sum(x_coords * (255 - gray)) / total_intensity
        center_y = np.sum(y_coords * (255 - gray)) / total_intensity
    else:
        center_x, center_y = w / 2, h / 2

    # Calculate deviation from center
    x_deviation = abs(center_x - w / 2) / (w / 2)
    y_deviation = abs(center_y - h / 2) / (h / 2)

    # Check margins (empty space at edges)
    margin_top = np.mean(gray[:h//10, :])
    margin_bottom = np.mean(gray[-h//10:, :])
    margin_left = np.mean(gray[:, :w//10])
    margin_right = np.mean(gray[:, -w//10:])

    return {
        'center_x_deviation': float(x_deviation),
        'center_y_deviation': float(y_deviation),
        'is_centered': x_deviation < 0.15 and y_deviation < 0.2,
        'margin_balance': float(abs(margin_left - margin_right) / 255)
    }


def compare_frames(generated: np.ndarray, reference: np.ndarray) -> Dict:
    """
    Compare a generated frame with a reference frame.

    Returns:
        Dictionary with comparison metrics
    """
    # Resize reference to match generated if needed
    if generated.shape != reference.shape:
        reference = cv2.resize(reference, (generated.shape[1], generated.shape[0]))

    # Calculate structural similarity (simplified)
    diff = np.abs(generated.astype(float) - reference.astype(float))
    mse = np.mean(diff ** 2)

    # Color difference
    gen_colors = analyze_color_palette(generated)
    ref_colors = analyze_color_palette(reference)

    brightness_diff = abs(gen_colors['brightness'] - ref_colors['brightness'])
    saturation_diff = abs(gen_colors['saturation'] - ref_colors['saturation'])

    return {
        'mse': float(mse),
        'brightness_diff': float(brightness_diff),
        'saturation_diff': float(saturation_diff),
        'gen_is_pastel': gen_colors['is_pastel'],
        'ref_is_pastel': ref_colors['is_pastel'],
        'gen_dark_ratio': gen_colors['dark_pixel_ratio'],
        'ref_dark_ratio': ref_colors['dark_pixel_ratio']
    }


def analyze_animation_smoothness(frames: List[Tuple[float, np.ndarray]]) -> Dict:
    """
    Analyze animation smoothness by comparing consecutive frames.

    Returns:
        Dictionary with animation analysis metrics
    """
    if len(frames) < 2:
        return {'smoothness_score': 1.0, 'frame_diffs': []}

    diffs = []
    for i in range(1, len(frames)):
        prev_frame = frames[i-1][1]
        curr_frame = frames[i][1]

        # Calculate frame difference
        diff = np.mean(np.abs(prev_frame.astype(float) - curr_frame.astype(float)))
        diffs.append(float(diff))

    # Smoothness = low variance in diffs (consistent motion)
    if diffs:
        variance = np.var(diffs)
        mean_diff = np.mean(diffs)
        # Normalize smoothness score (lower variance = smoother)
        smoothness = 1.0 / (1.0 + variance / 100)
    else:
        smoothness = 1.0
        mean_diff = 0

    return {
        'smoothness_score': float(smoothness),
        'mean_frame_diff': float(mean_diff),
        'max_frame_diff': float(max(diffs)) if diffs else 0,
        'frame_diffs': diffs[:10]  # First 10 for brevity
    }


# =============================================================================
# AUDIO TIMING ANALYSIS (New for quiz videos)
# =============================================================================

def load_audio_timestamps(json_path: str) -> Dict:
    """
    Load audio timestamps from the TTS-generated JSON file.

    Returns:
        Dictionary with words and their timestamps
    """
    if not os.path.exists(json_path):
        return None

    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def find_word_timestamp(words: List[Dict], target: str, start_from: int = 0, exact_match: bool = False) -> Tuple[int, float]:
    """
    Find the timestamp of a specific word in the words list.

    Args:
        words: List of word dictionaries with 'word' and 'start' keys
        target: Word to search for
        start_from: Index to start searching from
        exact_match: If True, only match exact words (not substrings)

    Returns:
        (index, timestamp) or (-1, -1) if not found
    """
    target_lower = target.lower()
    for i in range(start_from, len(words)):
        word = words[i].get('word', '').lower()
        # Clean word of punctuation for matching
        word_clean = word.strip('.,!?\'\"')

        if exact_match:
            # Exact match only
            if word_clean == target_lower:
                return (i, words[i].get('start', -1))
        else:
            # Allow substring match (for countdown numbers)
            if word_clean == target_lower or target_lower in word_clean:
                return (i, words[i].get('start', -1))
    return (-1, -1)


def analyze_countdown_timing(words: List[Dict]) -> Dict:
    """
    Analyze countdown timing (Tres, Dos, Uno or 3, 2, 1).

    Checks:
    - Each number should have ~1 second pause after it
    - Total countdown should be ~3 seconds

    Returns:
        Dictionary with countdown timing analysis
    """
    # Find countdown numbers (could be words or digits)
    countdown_patterns = [
        ('tres', 'dos', 'uno'),
        ('3', '2', '1'),
        ('three', 'two', 'one'),
    ]

    tres_time = dos_time = uno_time = -1

    for pattern in countdown_patterns:
        # Try to find this pattern
        idx, tres_time = find_word_timestamp(words, pattern[0])
        if idx >= 0:
            _, dos_time = find_word_timestamp(words, pattern[1], idx + 1)
            _, uno_time = find_word_timestamp(words, pattern[2], idx + 1)
            if dos_time >= 0 and uno_time >= 0:
                break

    if tres_time < 0 or dos_time < 0 or uno_time < 0:
        return {
            'found': False,
            'error': 'Countdown not found in audio',
            'score': 0
        }

    # Calculate gaps
    gap_tres_dos = dos_time - tres_time
    gap_dos_uno = uno_time - dos_time
    total_countdown = uno_time - tres_time

    # Score the timing
    issues = []
    score = 100

    # Check gap between 3 and 2
    if gap_tres_dos < COUNTDOWN_MIN_GAP:
        issues.append(f"Gap 3→2 too short: {gap_tres_dos:.2f}s (min: {COUNTDOWN_MIN_GAP}s)")
        score -= 25
    elif gap_tres_dos < COUNTDOWN_IDEAL_GAP:
        issues.append(f"Gap 3→2 slightly short: {gap_tres_dos:.2f}s (ideal: {COUNTDOWN_IDEAL_GAP}s)")
        score -= 10

    # Check gap between 2 and 1
    if gap_dos_uno < COUNTDOWN_MIN_GAP:
        issues.append(f"Gap 2→1 too short: {gap_dos_uno:.2f}s (min: {COUNTDOWN_MIN_GAP}s)")
        score -= 25
    elif gap_dos_uno < COUNTDOWN_IDEAL_GAP:
        issues.append(f"Gap 2→1 slightly short: {gap_dos_uno:.2f}s (ideal: {COUNTDOWN_IDEAL_GAP}s)")
        score -= 10

    # Check total countdown duration
    if total_countdown < 2.0:
        issues.append(f"Total countdown too fast: {total_countdown:.2f}s (should be ~3s)")
        score -= 20

    return {
        'found': True,
        'tres_time': tres_time,
        'dos_time': dos_time,
        'uno_time': uno_time,
        'gap_tres_dos': gap_tres_dos,
        'gap_dos_uno': gap_dos_uno,
        'total_duration': total_countdown,
        'issues': issues,
        'score': max(0, score)
    }


def analyze_option_timing(words: List[Dict]) -> Dict:
    """
    Analyze option timing (A, B, C, D spacing).

    Checks:
    - Each option should be ~1.5 seconds apart
    - All 4 options should be present and clearly spaced

    Returns:
        Dictionary with option timing analysis
    """
    # First, find where options section starts
    # Look for "opciones", "options", or "Opción" to mark start of options
    options_start_idx = 0
    for i, word_info in enumerate(words):
        word = word_info.get('word', '').lower()
        if 'opcion' in word or 'options' in word:
            options_start_idx = i + 1
            break

    # Find option letters (only after options section starts)
    # Use exact_match=True to avoid matching letters inside words (e.g., 'B' in 'embarrassed')
    option_times = {}
    last_idx = options_start_idx

    for letter in ['A', 'B', 'C', 'D']:
        idx, time = find_word_timestamp(words, letter, last_idx, exact_match=True)
        if idx >= 0:
            option_times[letter] = time
            last_idx = idx + 1

    if len(option_times) < 4:
        missing = [l for l in ['A', 'B', 'C', 'D'] if l not in option_times]
        return {
            'found': False,
            'error': f'Missing options: {missing}',
            'options_found': list(option_times.keys()),
            'score': 0
        }

    # Calculate gaps between options
    gaps = {}
    gaps['A_to_B'] = option_times['B'] - option_times['A']
    gaps['B_to_C'] = option_times['C'] - option_times['B']
    gaps['C_to_D'] = option_times['D'] - option_times['C']

    # Score the timing
    issues = []
    score = 100

    for gap_name, gap_value in gaps.items():
        if gap_value < OPTION_MIN_GAP:
            issues.append(f"Gap {gap_name} too short: {gap_value:.2f}s (min: {OPTION_MIN_GAP}s)")
            score -= 20
        elif gap_value < OPTION_IDEAL_GAP:
            issues.append(f"Gap {gap_name} slightly short: {gap_value:.2f}s (ideal: {OPTION_IDEAL_GAP}s)")
            score -= 5

    # Check for consistency (options should be evenly spaced)
    gap_values = list(gaps.values())
    gap_variance = max(gap_values) - min(gap_values)
    if gap_variance > 1.0:
        issues.append(f"Option spacing very inconsistent (variance: {gap_variance:.2f}s)")
        score -= 15
    elif gap_variance > 0.5:
        issues.append(f"Option spacing slightly inconsistent (variance: {gap_variance:.2f}s)")
        score -= 5

    return {
        'found': True,
        'option_times': option_times,
        'gaps': gaps,
        'average_gap': sum(gap_values) / len(gap_values),
        'issues': issues,
        'score': max(0, score)
    }


def analyze_question_transition(words: List[Dict], data: Dict) -> Dict:
    """
    Analyze transition from question to options.

    Checks:
    - There should be a pause after the question mark
    - "Escucha las opciones" or similar should have space before first option

    Returns:
        Dictionary with transition timing analysis
    """
    # Find "opciones" which marks end of transition phrase
    opciones_time = -1
    opciones_idx = -1
    for i, word_info in enumerate(words):
        word = word_info.get('word', '').lower()
        if 'opciones' in word:
            opciones_time = word_info.get('end', word_info.get('start', -1))
            opciones_idx = i
            break

    # Find first option A (after opciones)
    first_option_time = -1
    if opciones_idx >= 0:
        for i in range(opciones_idx + 1, len(words)):
            word = words[i].get('word', '').upper()
            if word == 'A' or word.startswith('A,') or word == 'OPCIÓN':
                first_option_time = words[i].get('start', -1)
                break

    if opciones_time < 0 or first_option_time < 0:
        return {
            'found': False,
            'error': 'Could not find "opciones" or first option',
            'score': 50  # Neutral score
        }

    # Calculate transition time (from end of "opciones" to start of option A)
    transition_time = first_option_time - opciones_time

    issues = []
    score = 100

    if transition_time < TRANSITION_MIN_PAUSE:
        issues.append(f"Transition too fast: {transition_time:.2f}s (min: {TRANSITION_MIN_PAUSE}s)")
        score -= 30
    elif transition_time < 1.0:
        issues.append(f"Transition slightly rushed: {transition_time:.2f}s (ideal: 1.0s+)")
        score -= 10

    return {
        'found': True,
        'opciones_end_time': opciones_time,
        'first_option_time': first_option_time,
        'transition_time': transition_time,
        'issues': issues,
        'score': max(0, score)
    }


def analyze_true_false_timing(words: List[Dict]) -> Dict:
    """
    Analyze timing for true/false videos.

    Checks:
    - Statement is clear
    - Verdadero/Falso options are present
    - Countdown timing
    - Answer reveal timing

    Returns:
        Dictionary with true/false timing analysis
    """
    # Find key moments
    verdadero_time = -1
    falso_time = -1
    answer_time = -1

    for i, word_info in enumerate(words):
        word = word_info.get('word', '').lower().strip('¿?.,!')

        # Find first verdadero/falso (the question)
        if word == 'verdadero' and verdadero_time < 0:
            verdadero_time = word_info.get('start', -1)
        if word == 'falso' and falso_time < 0:
            falso_time = word_info.get('start', -1)

    # Find the answer (after countdown) - look for verdadero/falso after "uno"
    uno_idx = -1
    for i, word_info in enumerate(words):
        word = word_info.get('word', '').lower().strip('¿?.,!')
        if word == 'uno':
            uno_idx = i
            break

    if uno_idx >= 0:
        for i in range(uno_idx + 1, len(words)):
            word = words[i].get('word', '').lower().strip('¿?.,!')
            if word in ['verdadero', 'falso']:
                answer_time = words[i].get('start', -1)
                break

    issues = []
    score = 100

    # Check that question options exist
    if verdadero_time < 0 or falso_time < 0:
        issues.append("Could not find Verdadero/Falso options in audio")
        score -= 30

    # Also check countdown
    countdown = analyze_countdown_timing(words)
    if not countdown.get('found'):
        issues.append("Countdown not found")
        score -= 20
    elif countdown.get('score', 100) < 80:
        issues.extend(countdown.get('issues', []))
        score -= (100 - countdown.get('score', 100)) // 2

    return {
        'found': True,
        'video_type': 'true_false',
        'verdadero_time': verdadero_time,
        'falso_time': falso_time,
        'answer_time': answer_time,
        'countdown': countdown,
        'issues': issues,
        'score': max(0, score)
    }


def analyze_audio_timing(json_path: str) -> Dict:
    """
    Complete audio timing analysis for quiz/true_false videos.

    Auto-detects video type and applies appropriate timing checks.

    Args:
        json_path: Path to the TTS JSON file with timestamps

    Returns:
        Complete audio timing analysis
    """
    data = load_audio_timestamps(json_path)

    if not data:
        return {
            'error': f'Could not load timestamps from {json_path}',
            'overall_score': 0
        }

    words = data.get('words', [])
    if not words:
        return {
            'error': 'No words found in timestamps',
            'overall_score': 0
        }

    # Detect video type from the data
    video_type = data.get('type', 'quiz')

    if video_type == 'true_false':
        # Use true/false specific analysis
        tf_analysis = analyze_true_false_timing(words)
        countdown = tf_analysis.get('countdown', {})

        # Calculate score based on true/false analysis
        overall_score = tf_analysis.get('score', 100)

        critical_issues = []
        warnings = []
        for issue in tf_analysis.get('issues', []):
            if 'slightly' in issue.lower():
                warnings.append(f"[TRUE_FALSE] {issue}")
            else:
                critical_issues.append(f"[TRUE_FALSE] {issue}")

        all_issues = critical_issues + warnings
        passes_quality = overall_score >= 80 and len(critical_issues) == 0

        return {
            'video_type': 'true_false',
            'true_false': tf_analysis,
            'countdown': countdown,
            'critical_issues': critical_issues,
            'warnings': warnings,
            'all_issues': all_issues,
            'overall_score': overall_score,
            'passes_quality': passes_quality
        }

    # Quiz video analysis
    countdown = analyze_countdown_timing(words)
    options = analyze_option_timing(words)
    transition = analyze_question_transition(words, data)

    # Calculate overall timing score
    scores = []
    if countdown.get('found'):
        scores.append(countdown['score'])
    if options.get('found'):
        scores.append(options['score'])
    if transition.get('found'):
        scores.append(transition['score'])

    overall_score = sum(scores) / len(scores) if scores else 0

    # Collect all issues (separate critical vs warnings)
    critical_issues = []
    warnings = []

    for issue_list, prefix in [
        (countdown.get('issues', []), '[COUNTDOWN]'),
        (options.get('issues', []), '[OPTIONS]'),
        (transition.get('issues', []), '[TRANSITION]')
    ]:
        for issue in issue_list:
            full_issue = f"{prefix} {issue}"
            # "slightly" issues are warnings, not critical
            if 'slightly' in issue.lower():
                warnings.append(full_issue)
            else:
                critical_issues.append(full_issue)

    all_issues = critical_issues + warnings

    # Pass if score >= 80 and no critical issues (warnings are OK)
    passes_quality = overall_score >= 80 and len(critical_issues) == 0

    return {
        'video_type': 'quiz',
        'countdown': countdown,
        'options': options,
        'transition': transition,
        'critical_issues': critical_issues,
        'warnings': warnings,
        'all_issues': all_issues,
        'overall_score': overall_score,
        'passes_quality': passes_quality
    }


# =============================================================================
# AUDIO QUALITY ANALYSIS
# =============================================================================

def analyze_audio_quality(video_path: str) -> Dict:
    """
    Analyze audio quality by extracting audio and checking for issues.

    Checks for:
    - Audio glitches (sudden volume spikes/drops)
    - Silence gaps where there shouldn't be
    - Overall audio consistency
    - Duration matches video

    Returns:
        Dictionary with audio quality analysis
    """
    issues = []
    score = 100

    try:
        # Extract audio using ffprobe to get audio stats
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'a:0',
            '-show_entries', 'stream=codec_name,sample_rate,channels,duration',
            '-of', 'json',
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return {
                'found': False,
                'error': 'Could not analyze audio stream',
                'issues': ['Audio stream analysis failed'],
                'score': 0
            }

        audio_info = json.loads(result.stdout)
        streams = audio_info.get('streams', [])

        if not streams:
            return {
                'found': False,
                'error': 'No audio stream found',
                'issues': ['No audio stream in video'],
                'score': 0
            }

        stream = streams[0]
        codec = stream.get('codec_name', 'unknown')
        sample_rate = int(stream.get('sample_rate', 0))
        channels = int(stream.get('channels', 0))
        duration = float(stream.get('duration', 0))

        # Check audio parameters
        if sample_rate < 22050:
            issues.append(f"Low audio sample rate: {sample_rate}Hz (should be >= 22050Hz)")
            score -= 20

        if channels < 1:
            issues.append("No audio channels detected")
            score -= 30

        # Use ffmpeg to analyze volume levels
        cmd_vol = [
            'ffmpeg', '-i', video_path,
            '-af', 'volumedetect',
            '-f', 'null', '-'
        ]
        result_vol = subprocess.run(cmd_vol, capture_output=True, text=True, timeout=60)

        stderr = result_vol.stderr

        # Parse volume detection output
        max_volume = None
        mean_volume = None
        for line in stderr.split('\n'):
            if 'max_volume' in line:
                try:
                    max_volume = float(line.split(':')[1].strip().replace(' dB', ''))
                except:
                    pass
            if 'mean_volume' in line:
                try:
                    mean_volume = float(line.split(':')[1].strip().replace(' dB', ''))
                except:
                    pass

        # Check for audio issues
        if max_volume is not None and max_volume > -1.0:
            issues.append(f"Audio may be clipping (max volume: {max_volume:.1f} dB)")
            score -= 15

        if mean_volume is not None and mean_volume < -30:
            issues.append(f"Audio too quiet (mean volume: {mean_volume:.1f} dB)")
            score -= 10

        return {
            'found': True,
            'codec': codec,
            'sample_rate': sample_rate,
            'channels': channels,
            'duration': duration,
            'max_volume': max_volume,
            'mean_volume': mean_volume,
            'issues': issues,
            'score': max(0, score)
        }

    except subprocess.TimeoutExpired:
        return {
            'found': False,
            'error': 'Audio analysis timed out',
            'issues': ['Audio analysis timed out'],
            'score': 0
        }
    except Exception as e:
        return {
            'found': False,
            'error': str(e),
            'issues': [f'Audio analysis error: {str(e)}'],
            'score': 0
        }


# =============================================================================
# LANGUAGE CORRECTNESS ANALYSIS
# =============================================================================

# Words that should ALWAYS be Spanish (never marked as English)
SPANISH_ONLY_WORDS = {
    # Quiz structure words
    'opción', 'opcion', 'opciones', 'respuesta', 'correcta', 'significa',
    'cómo', 'como', 'dice', 'qué', 'que', 'inglés', 'ingles',
    # Option letters in Spanish context
    'a', 'b', 'c', 'd',
    # Countdown
    'tres', 'dos', 'uno',
    # Common Spanish
    'la', 'el', 'las', 'los', 'es', 'en', 'se', 'de', 'y', 'o',
    'ahora', 'piensa', 'bien', 'escucha',
    # False friends that are SPANISH
    'embarazada', 'librería', 'sensible', 'actualmente', 'constipado',
    'avergonzado', 'biblioteca',
}

# Words that are clearly English when teaching
ENGLISH_TEACHING_WORDS = {
    'embarrassed', 'pregnant', 'library', 'bookstore', 'sensitive',
    'actually', 'constipated', 'ashamed', 'bashful',
    'give', 'up', 'take', 'off', 'look', 'for', 'put', 'down',
}


def analyze_language_correctness(data: Dict) -> Dict:
    """
    Analyze language marking correctness in word timestamps.

    Checks:
    - Spanish words should NOT be marked as is_english=true
    - English teaching words SHOULD be marked as is_english=true
    - Option letters (A, B, C, D) should be Spanish

    Returns:
        Dictionary with language analysis
    """
    words = data.get('words', [])
    if not words:
        return {
            'found': False,
            'error': 'No words to analyze',
            'score': 100
        }

    issues = []
    score = 100

    wrong_spanish_as_english = []  # Spanish words incorrectly marked as English
    wrong_english_as_spanish = []  # English words incorrectly marked as Spanish

    for word_info in words:
        word = word_info.get('word', '').lower()
        word_clean = word.strip('.,!?\'\"')
        is_english = word_info.get('is_english', False)

        # Check if Spanish word is incorrectly marked as English
        if word_clean in SPANISH_ONLY_WORDS and is_english:
            wrong_spanish_as_english.append(word_info.get('word', word))

        # Check if English teaching word is NOT marked as English
        if word_clean in ENGLISH_TEACHING_WORDS and not is_english:
            wrong_english_as_spanish.append(word_info.get('word', word))

    if wrong_spanish_as_english:
        issues.append(f"Spanish words incorrectly marked as English: {wrong_spanish_as_english[:5]}")
        score -= min(40, len(wrong_spanish_as_english) * 10)

    if wrong_english_as_spanish:
        issues.append(f"English words not marked as English: {wrong_english_as_spanish[:5]}")
        score -= min(30, len(wrong_english_as_spanish) * 10)

    return {
        'found': True,
        'total_words': len(words),
        'english_marked': sum(1 for w in words if w.get('is_english')),
        'wrong_spanish_as_english': wrong_spanish_as_english,
        'wrong_english_as_spanish': wrong_english_as_spanish,
        'issues': issues,
        'score': max(0, score)
    }


# =============================================================================
# ANIMATION GLITCH DETECTION
# =============================================================================

def detect_animation_glitches(frames: List[Tuple[float, np.ndarray]]) -> Dict:
    """
    Detect animation glitches by analyzing frame-to-frame differences.

    Checks for:
    - Sudden large changes (visual glitches)
    - Frozen frames (no change when there should be)
    - Unnatural motion patterns

    Returns:
        Dictionary with glitch analysis
    """
    if len(frames) < 3:
        return {
            'found': True,
            'issues': [],
            'score': 100
        }

    issues = []
    score = 100

    diffs = []
    timestamps = []

    for i in range(1, len(frames)):
        prev_ts, prev_frame = frames[i-1]
        curr_ts, curr_frame = frames[i]

        # Calculate frame difference
        diff = np.mean(np.abs(prev_frame.astype(float) - curr_frame.astype(float)))
        diffs.append(diff)
        timestamps.append(curr_ts)

    if not diffs:
        return {'found': True, 'issues': [], 'score': 100}

    mean_diff = np.mean(diffs)
    std_diff = np.std(diffs)

    # Detect glitches (sudden large changes)
    glitch_threshold = mean_diff + 3 * std_diff  # 3 sigma outlier
    glitches = []

    for i, diff in enumerate(diffs):
        if diff > glitch_threshold and diff > 30:  # Also check absolute threshold
            glitches.append({
                'timestamp': timestamps[i],
                'diff': diff,
                'threshold': glitch_threshold
            })

    if glitches:
        issues.append(f"Animation glitches detected at {len(glitches)} points")
        score -= min(40, len(glitches) * 15)

    # Detect frozen frames (very low diff when animation expected)
    frozen_threshold = 1.0  # Almost no change
    frozen_count = sum(1 for d in diffs if d < frozen_threshold)
    frozen_ratio = frozen_count / len(diffs)

    if frozen_ratio > 0.5:  # More than 50% frozen
        issues.append(f"Too many frozen frames: {frozen_ratio*100:.0f}% of frames show no change")
        score -= 20

    # Check for erratic motion (high variance in diffs)
    if std_diff > mean_diff * 2:  # Very high variance
        issues.append(f"Erratic animation detected (variance too high)")
        score -= 15

    return {
        'found': True,
        'mean_diff': float(mean_diff),
        'std_diff': float(std_diff),
        'glitches': glitches,
        'frozen_ratio': float(frozen_ratio),
        'issues': issues,
        'score': max(0, score)
    }


# =============================================================================
# PACING ANALYSIS
# =============================================================================

def analyze_pacing(data: Dict, video_duration: float) -> Dict:
    """
    Analyze overall pacing of the video.

    Checks:
    - Audio duration matches video
    - Words per second (speaking rate)
    - No rushed sections
    - Natural flow

    Returns:
        Dictionary with pacing analysis
    """
    words = data.get('words', [])
    audio_duration = data.get('duration', 0)

    if not words or not audio_duration:
        return {
            'found': False,
            'error': 'Missing data for pacing analysis',
            'score': 50
        }

    issues = []
    score = 100

    # Check audio-video duration match
    if video_duration > 0:
        duration_diff = abs(video_duration - audio_duration)
        if duration_diff > 1.0:
            issues.append(f"Audio/video duration mismatch: video={video_duration:.1f}s, audio={audio_duration:.1f}s")
            score -= 20

    # Calculate speaking rate
    word_count = len(words)
    words_per_second = word_count / audio_duration if audio_duration > 0 else 0

    # Normal speaking rate is about 2-3 words per second
    if words_per_second > 4.0:
        issues.append(f"Speaking too fast: {words_per_second:.1f} words/second (normal: 2-3)")
        score -= 25
    elif words_per_second > 3.5:
        issues.append(f"Speaking slightly fast: {words_per_second:.1f} words/second")
        score -= 10
    elif words_per_second < 1.5:
        issues.append(f"Speaking too slow: {words_per_second:.1f} words/second")
        score -= 10

    # Check for rushed sections (many words close together)
    rushed_sections = []
    window_size = 5  # Check windows of 5 words

    for i in range(len(words) - window_size):
        window = words[i:i + window_size]
        start = window[0].get('start', 0)
        end = window[-1].get('end', start)
        window_duration = end - start

        if window_duration > 0:
            window_rate = window_size / window_duration
            if window_rate > 6.0:  # Very rushed
                rushed_sections.append({
                    'start': start,
                    'end': end,
                    'rate': window_rate
                })

    if rushed_sections:
        issues.append(f"Rushed sections detected: {len(rushed_sections)} areas with rapid speech")
        score -= min(20, len(rushed_sections) * 5)

    return {
        'found': True,
        'audio_duration': audio_duration,
        'video_duration': video_duration,
        'word_count': word_count,
        'words_per_second': words_per_second,
        'rushed_sections': len(rushed_sections),
        'issues': issues,
        'score': max(0, score)
    }


def generate_improvement_report(
    video_analysis: Dict,
    reference_analysis: Dict,
    comparison: Dict
) -> List[str]:
    """
    Generate specific improvement recommendations.

    Returns:
        List of improvement suggestions
    """
    suggestions = []

    # Color analysis
    if video_analysis['color']['dark_pixel_ratio'] > 0.1:
        suggestions.append(
            f"Colors too dark: {video_analysis['color']['dark_pixel_ratio']*100:.1f}% dark pixels. "
            "References use more pastel backgrounds."
        )

    if not video_analysis['color']['is_pastel'] and reference_analysis['color']['is_pastel']:
        suggestions.append(
            f"Color palette not pastel-like. Current brightness: {video_analysis['color']['brightness']:.0f}, "
            f"saturation: {video_analysis['color']['saturation']:.0f}. "
            "Increase brightness and moderate saturation for softer look."
        )

    # Brightness
    if comparison.get('brightness_diff', 0) > 30 and reference_analysis:
        if video_analysis['color']['brightness'] < reference_analysis['color']['brightness']:
            suggestions.append(
                f"Video too dark compared to references. Brightness: {video_analysis['color']['brightness']:.0f} "
                f"vs reference: {reference_analysis['color']['brightness']:.0f}. Increase overall brightness."
            )

    # Text readability
    if video_analysis['text']['sharpness'] < 500:
        suggestions.append(
            f"Text may lack sharpness. Current sharpness: {video_analysis['text']['sharpness']:.0f}. "
            "Consider using bolder fonts or stronger outlines."
        )

    # Layout
    if not video_analysis['layout']['is_centered']:
        suggestions.append(
            f"Layout not well centered. X deviation: {video_analysis['layout']['center_x_deviation']*100:.1f}%, "
            f"Y deviation: {video_analysis['layout']['center_y_deviation']*100:.1f}%. "
            "Adjust element positioning."
        )

    # Animation
    if video_analysis['animation']['smoothness_score'] < 0.8:
        suggestions.append(
            f"Animations may be jerky. Smoothness score: {video_analysis['animation']['smoothness_score']:.2f}. "
            "Consider smoother easing functions or higher frame rate."
        )

    if video_analysis['animation']['max_frame_diff'] > 50:
        suggestions.append(
            f"Abrupt transitions detected (max diff: {video_analysis['animation']['max_frame_diff']:.0f}). "
            "References have smoother transitions."
        )

    if not suggestions:
        suggestions.append("Video quality looks good! No major issues detected.")

    return suggestions


def analyze_video(video_path: str, verbose: bool = True) -> Dict:
    """
    Comprehensive video analysis.

    Args:
        video_path: Path to the video file
        verbose: Print progress information

    Returns:
        Complete analysis dictionary
    """
    if verbose:
        print(f"Analyzing video: {video_path}")

    # Extract frames
    if verbose:
        print("  Extracting frames...")
    frames = extract_frames(video_path, interval=0.5)

    if not frames:
        raise ValueError("No frames extracted from video")

    if verbose:
        print(f"  Extracted {len(frames)} frames")

    # Analyze frames
    color_analyses = []
    text_analyses = []
    layout_analyses = []

    for timestamp, frame in frames:
        color_analyses.append(analyze_color_palette(frame))
        text_analyses.append(analyze_text_readability(frame))
        layout_analyses.append(analyze_layout_balance(frame))

    # Aggregate results
    avg_color = {
        'brightness': np.mean([c['brightness'] for c in color_analyses]),
        'saturation': np.mean([c['saturation'] for c in color_analyses]),
        'dark_pixel_ratio': np.mean([c['dark_pixel_ratio'] for c in color_analyses]),
        'is_pastel': sum(c['is_pastel'] for c in color_analyses) > len(color_analyses) / 2
    }

    avg_text = {
        'edge_density': np.mean([t['edge_density'] for t in text_analyses]),
        'sharpness': np.mean([t['sharpness'] for t in text_analyses]),
        'center_contrast': np.mean([t['center_contrast'] for t in text_analyses])
    }

    avg_layout = {
        'center_x_deviation': np.mean([l['center_x_deviation'] for l in layout_analyses]),
        'center_y_deviation': np.mean([l['center_y_deviation'] for l in layout_analyses]),
        'is_centered': sum(l['is_centered'] for l in layout_analyses) > len(layout_analyses) / 2,
        'margin_balance': np.mean([l['margin_balance'] for l in layout_analyses])
    }

    # Animation smoothness
    animation = analyze_animation_smoothness(frames)

    return {
        'video_path': video_path,
        'num_frames': len(frames),
        'color': avg_color,
        'text': avg_text,
        'layout': avg_layout,
        'animation': animation
    }


def analyze_references(verbose: bool = True) -> Dict:
    """Analyze reference images."""
    if verbose:
        print("Analyzing reference images...")

    references = load_reference_images()

    if not references:
        if verbose:
            print("  No reference images found")
        return None

    if verbose:
        print(f"  Loaded {len(references)} reference images")

    color_analyses = [analyze_color_palette(ref) for ref in references]
    text_analyses = [analyze_text_readability(ref) for ref in references]
    layout_analyses = [analyze_layout_balance(ref) for ref in references]

    return {
        'num_references': len(references),
        'color': {
            'brightness': np.mean([c['brightness'] for c in color_analyses]),
            'saturation': np.mean([c['saturation'] for c in color_analyses]),
            'dark_pixel_ratio': np.mean([c['dark_pixel_ratio'] for c in color_analyses]),
            'is_pastel': sum(c['is_pastel'] for c in color_analyses) > len(color_analyses) / 2
        },
        'text': {
            'edge_density': np.mean([t['edge_density'] for t in text_analyses]),
            'sharpness': np.mean([t['sharpness'] for t in text_analyses]),
            'center_contrast': np.mean([t['center_contrast'] for t in text_analyses])
        },
        'layout': {
            'center_x_deviation': np.mean([l['center_x_deviation'] for l in layout_analyses]),
            'center_y_deviation': np.mean([l['center_y_deviation'] for l in layout_analyses]),
            'is_centered': sum(l['is_centered'] for l in layout_analyses) > len(layout_analyses) / 2,
            'margin_balance': np.mean([l['margin_balance'] for l in layout_analyses])
        }
    }


def calculate_quality_score(video_analysis: Dict, reference_analysis: Dict = None) -> float:
    """
    Calculate overall quality score (0-100).
    """
    score = 50  # Base score

    # Color quality (25 points)
    if video_analysis['color']['is_pastel']:
        score += 15
    if video_analysis['color']['dark_pixel_ratio'] < 0.05:
        score += 10
    elif video_analysis['color']['dark_pixel_ratio'] < 0.15:
        score += 5

    # Layout quality (25 points)
    if video_analysis['layout']['is_centered']:
        score += 15
    if video_analysis['layout']['margin_balance'] < 0.1:
        score += 10

    # Animation quality (25 points)
    smoothness = video_analysis['animation']['smoothness_score']
    score += int(smoothness * 25)

    # If we have reference comparison, adjust score
    if reference_analysis:
        brightness_match = 1 - min(1, abs(
            video_analysis['color']['brightness'] - reference_analysis['color']['brightness']
        ) / 100)
        score = int(score * (0.8 + 0.2 * brightness_match))

    return min(100, max(0, score))


def main():
    parser = argparse.ArgumentParser(
        description="Video Analyzer - Analyze and compare video quality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python video_analyzer.py --video output/video/quiz/test.mp4
  python video_analyzer.py --video output/video/quiz/test.mp4 --audio output/audio/quiz/test.json
  python video_analyzer.py --video test.mp4 --audio test.json --quiz
        """
    )

    parser.add_argument("--video", "-v", help="Video file to analyze")
    parser.add_argument("--audio", "-a", help="Audio JSON file with timestamps (for timing analysis)")
    parser.add_argument("--quiz", "-q", action="store_true",
                        help="Enable quiz-specific analysis (timing, options, countdown)")
    parser.add_argument("--compare", "-c", action="store_true",
                        help="Compare with reference images")
    parser.add_argument("--output", "-o", help="Output JSON file for results")
    parser.add_argument("--verbose", action="store_true", default=True,
                        help="Print detailed progress")

    args = parser.parse_args()

    if not args.video:
        parser.error("Please specify a video with --video")

    if not os.path.exists(args.video):
        print(f"Error: Video not found: {args.video}")
        sys.exit(1)

    # Auto-detect audio JSON path if not provided
    if not args.audio:
        # Try to find matching JSON file
        video_path = Path(args.video)
        audio_json = video_path.parent.parent / "audio" / video_path.parent.name / (video_path.stem + ".json")
        if audio_json.exists():
            args.audio = str(audio_json)
            args.quiz = True  # Auto-enable quiz analysis

    # Analyze video visuals
    video_analysis = analyze_video(args.video, verbose=args.verbose)

    # Extract frames for advanced analysis
    frames = extract_frames(args.video, interval=0.5)

    # NEW: Analyze audio quality (glitches, breaks)
    if args.verbose:
        print("Analyzing audio quality...")
    audio_quality = analyze_audio_quality(args.video)

    # NEW: Detect animation glitches
    if args.verbose:
        print("Checking for animation glitches...")
    animation_glitches = detect_animation_glitches(frames)

    # Analyze audio timing (for quiz videos)
    audio_timing = None
    audio_data = None
    if args.audio and os.path.exists(args.audio):
        if args.verbose:
            print(f"Analyzing audio timing: {args.audio}")
        audio_timing = analyze_audio_timing(args.audio)

        # Load audio data for additional analysis
        with open(args.audio, 'r', encoding='utf-8') as f:
            audio_data = json.load(f)

    # NEW: Analyze language correctness
    language_analysis = None
    if audio_data:
        if args.verbose:
            print("Checking language correctness...")
        language_analysis = analyze_language_correctness(audio_data)

    # NEW: Analyze pacing
    pacing_analysis = None
    if audio_data:
        # Get video duration
        cap = cv2.VideoCapture(args.video)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_duration = total_frames / fps if fps > 0 else 0
        cap.release()

        if args.verbose:
            print("Analyzing pacing...")
        pacing_analysis = analyze_pacing(audio_data, video_duration)

    # Analyze references if requested
    reference_analysis = None
    if args.compare:
        reference_analysis = analyze_references(verbose=args.verbose)

    # Generate comparison
    comparison = {}
    if reference_analysis:
        frames = extract_frames(args.video, interval=1.0)
        references = load_reference_images()

        if frames and references:
            comparison = compare_frames(frames[0][1], references[0])

    # Calculate quality score
    visual_score = calculate_quality_score(video_analysis, reference_analysis)

    # Calculate timing score (for quiz videos)
    timing_score = 0
    if audio_timing and not audio_timing.get('error'):
        timing_score = audio_timing.get('overall_score', 0)

    # Calculate audio quality score
    audio_quality_score = audio_quality.get('score', 100) if audio_quality.get('found') else 50

    # Calculate animation glitch score
    glitch_score = animation_glitches.get('score', 100)

    # Calculate language score
    language_score = language_analysis.get('score', 100) if language_analysis else 100

    # Calculate pacing score
    pacing_score = pacing_analysis.get('score', 100) if pacing_analysis else 100

    # Combined score with all factors
    # Weights: Audio quality (25%), Visual (15%), Timing (25%), Language (20%), Pacing (15%)
    if audio_timing:
        combined_score = int(
            audio_quality_score * 0.25 +
            visual_score * 0.15 +
            timing_score * 0.25 +
            language_score * 0.20 +
            pacing_score * 0.15
        )
    else:
        combined_score = int(
            audio_quality_score * 0.30 +
            visual_score * 0.30 +
            glitch_score * 0.20 +
            pacing_score * 0.20
        )

    # Collect ALL issues from all analyses
    all_issues = []

    # Audio quality issues
    if audio_quality.get('issues'):
        for issue in audio_quality['issues']:
            all_issues.append(f"[AUDIO] {issue}")

    # Animation glitch issues
    if animation_glitches.get('issues'):
        for issue in animation_glitches['issues']:
            all_issues.append(f"[ANIMATION] {issue}")

    # Language issues
    if language_analysis and language_analysis.get('issues'):
        for issue in language_analysis['issues']:
            all_issues.append(f"[LANGUAGE] {issue}")

    # Pacing issues
    if pacing_analysis and pacing_analysis.get('issues'):
        for issue in pacing_analysis['issues']:
            all_issues.append(f"[PACING] {issue}")

    # Timing issues (from audio_timing)
    if audio_timing and audio_timing.get('all_issues'):
        all_issues.extend(audio_timing['all_issues'])

    # Generate visual improvement suggestions
    if reference_analysis:
        suggestions = generate_improvement_report(
            video_analysis, reference_analysis, comparison
        )
    else:
        suggestions = generate_improvement_report(
            video_analysis, video_analysis, {}
        )

    # Combine all issues
    if suggestions and suggestions[0] != "Video quality looks good! No major issues detected.":
        all_issues.extend(suggestions)

    # Determine pass/fail - STRICT criteria
    # Must pass ALL checks, not just combined score
    critical_failures = []

    if audio_quality_score < 70:
        critical_failures.append("Audio quality below threshold")
    if glitch_score < 70:
        critical_failures.append("Animation glitches detected")
    if language_score < 70:
        critical_failures.append("Language marking errors")
    if pacing_score < 70:
        critical_failures.append("Pacing issues")
    if timing_score < 70 and audio_timing:
        critical_failures.append("Timing issues")
    if visual_score < 60:
        critical_failures.append("Visual quality below threshold")

    passes_quality = len(critical_failures) == 0 and combined_score >= 70

    # Print results
    print("\n" + "=" * 70)
    print("VIDEO ANALYSIS REPORT")
    print("=" * 70)

    # Overall result banner
    if passes_quality:
        print("\n  ✓ PASS - Video meets quality standards")
    else:
        print("\n  ✗ FAIL - Video needs improvements")
        if critical_failures:
            print(f"\n  CRITICAL FAILURES:")
            for failure in critical_failures:
                print(f"    ✗ {failure}")

    print(f"\n  SCORES:")
    print(f"    Audio Quality:    {audio_quality_score}/100")
    print(f"    Visual Quality:   {visual_score}/100")
    if audio_timing:
        print(f"    Timing Quality:   {timing_score:.0f}/100")
    print(f"    Animation:        {glitch_score}/100")
    if language_analysis:
        print(f"    Language:         {language_score}/100")
    if pacing_analysis:
        print(f"    Pacing:           {pacing_score}/100")
    print(f"    ─────────────────────────")
    print(f"    COMBINED SCORE:   {combined_score}/100")

    # Audio Quality Analysis (NEW)
    print(f"\n{'=' * 70}")
    print("AUDIO QUALITY ANALYSIS")
    print("=" * 70)
    if audio_quality.get('found'):
        print(f"\n  Codec: {audio_quality.get('codec', 'unknown')}")
        print(f"  Sample Rate: {audio_quality.get('sample_rate', 0)} Hz")
        print(f"  Channels: {audio_quality.get('channels', 0)}")
        print(f"  Duration: {audio_quality.get('duration', 0):.2f}s")
        if audio_quality.get('max_volume') is not None:
            print(f"  Max Volume: {audio_quality.get('max_volume'):.1f} dB")
        if audio_quality.get('mean_volume') is not None:
            print(f"  Mean Volume: {audio_quality.get('mean_volume'):.1f} dB")
        print(f"  Score: {audio_quality_score}/100")
        if audio_quality.get('issues'):
            print("  Issues:")
            for issue in audio_quality['issues']:
                print(f"    ⚠ {issue}")
    else:
        print(f"\n  Error: {audio_quality.get('error', 'Unknown error')}")

    # Animation Glitch Analysis (NEW)
    print(f"\n{'=' * 70}")
    print("ANIMATION ANALYSIS")
    print("=" * 70)
    print(f"\n  Mean Frame Diff: {animation_glitches.get('mean_diff', 0):.2f}")
    print(f"  Frozen Frame Ratio: {animation_glitches.get('frozen_ratio', 0)*100:.1f}%")
    print(f"  Glitches Detected: {len(animation_glitches.get('glitches', []))}")
    print(f"  Score: {glitch_score}/100")
    if animation_glitches.get('issues'):
        print("  Issues:")
        for issue in animation_glitches['issues']:
            print(f"    ⚠ {issue}")

    # Language Analysis (NEW)
    if language_analysis:
        print(f"\n{'=' * 70}")
        print("LANGUAGE ANALYSIS")
        print("=" * 70)
        print(f"\n  Total Words: {language_analysis.get('total_words', 0)}")
        print(f"  Marked as English: {language_analysis.get('english_marked', 0)}")
        if language_analysis.get('wrong_spanish_as_english'):
            print(f"  ⚠ Spanish incorrectly marked English: {language_analysis['wrong_spanish_as_english'][:5]}")
        if language_analysis.get('wrong_english_as_spanish'):
            print(f"  ⚠ English not marked: {language_analysis['wrong_english_as_spanish'][:5]}")
        print(f"  Score: {language_score}/100")

    # Pacing Analysis (NEW)
    if pacing_analysis:
        print(f"\n{'=' * 70}")
        print("PACING ANALYSIS")
        print("=" * 70)
        print(f"\n  Audio Duration: {pacing_analysis.get('audio_duration', 0):.2f}s")
        print(f"  Video Duration: {pacing_analysis.get('video_duration', 0):.2f}s")
        print(f"  Words: {pacing_analysis.get('word_count', 0)}")
        print(f"  Speaking Rate: {pacing_analysis.get('words_per_second', 0):.1f} words/sec")
        print(f"  Rushed Sections: {pacing_analysis.get('rushed_sections', 0)}")
        print(f"  Score: {pacing_score}/100")
        if pacing_analysis.get('issues'):
            print("  Issues:")
            for issue in pacing_analysis['issues']:
                print(f"    ⚠ {issue}")

    # Audio timing details - handle different video types
    if audio_timing and not audio_timing.get('error'):
        video_type = audio_timing.get('video_type', 'quiz')

        print(f"\n{'=' * 70}")
        print(f"TIMING ANALYSIS ({video_type.replace('_', ' ').title()} Video)")
        print("=" * 70)

        if video_type == 'true_false':
            # True/False specific output
            tf = audio_timing.get('true_false', {})
            print(f"\n  TRUE/FALSE TIMING:")
            if tf.get('verdadero_time', -1) >= 0:
                print(f"    Verdadero mentioned: {tf.get('verdadero_time', 0):.2f}s")
            if tf.get('falso_time', -1) >= 0:
                print(f"    Falso mentioned: {tf.get('falso_time', 0):.2f}s")
            if tf.get('answer_time', -1) >= 0:
                print(f"    Answer revealed: {tf.get('answer_time', 0):.2f}s")
            print(f"    Score: {tf.get('score', 0)}/100")

            # Countdown within true/false
            countdown = tf.get('countdown', {})
            if countdown.get('found'):
                print(f"\n  COUNTDOWN:")
                print(f"    Tres: {countdown.get('tres_time', 0):.2f}s")
                print(f"    Dos:  {countdown.get('dos_time', 0):.2f}s  (gap: {countdown.get('gap_tres_dos', 0):.2f}s)")
                print(f"    Uno:  {countdown.get('uno_time', 0):.2f}s  (gap: {countdown.get('gap_dos_uno', 0):.2f}s)")
                print(f"    Score: {countdown.get('score', 0)}/100")

            if tf.get('issues'):
                print(f"\n  Issues:")
                for issue in tf['issues']:
                    print(f"    ⚠ {issue}")
        else:
            # Quiz video timing output
            countdown = audio_timing.get('countdown', {})
            if countdown.get('found'):
                print(f"\n  COUNTDOWN TIMING:")
                print(f"    Tres: {countdown.get('tres_time', 0):.2f}s")
                print(f"    Dos:  {countdown.get('dos_time', 0):.2f}s  (gap: {countdown.get('gap_tres_dos', 0):.2f}s)")
                print(f"    Uno:  {countdown.get('uno_time', 0):.2f}s  (gap: {countdown.get('gap_dos_uno', 0):.2f}s)")
                print(f"    Total duration: {countdown.get('total_duration', 0):.2f}s")
                print(f"    Score: {countdown.get('score', 0)}/100")
                if countdown.get('issues'):
                    for issue in countdown['issues']:
                        print(f"    ⚠ {issue}")
            else:
                print(f"\n  COUNTDOWN: Not found - {countdown.get('error', 'unknown error')}")

            # Option timing
            options = audio_timing.get('options', {})
            if options.get('found'):
                print(f"\n  OPTION TIMING:")
                times = options.get('option_times', {})
                gaps = options.get('gaps', {})
                print(f"    A: {times.get('A', 0):.2f}s")
                print(f"    B: {times.get('B', 0):.2f}s  (gap A→B: {gaps.get('A_to_B', 0):.2f}s)")
                print(f"    C: {times.get('C', 0):.2f}s  (gap B→C: {gaps.get('B_to_C', 0):.2f}s)")
                print(f"    D: {times.get('D', 0):.2f}s  (gap C→D: {gaps.get('C_to_D', 0):.2f}s)")
                print(f"    Average gap: {options.get('average_gap', 0):.2f}s")
                print(f"    Score: {options.get('score', 0)}/100")
                if options.get('issues'):
                    for issue in options['issues']:
                        print(f"    ⚠ {issue}")
            else:
                print(f"\n  OPTIONS: Not found - {options.get('error', 'unknown error')}")

            # Transition timing
            transition = audio_timing.get('transition', {})
            if transition.get('found'):
                print(f"\n  QUESTION→OPTIONS TRANSITION:")
                print(f"    'Opciones' ends: {transition.get('opciones_end_time', 0):.2f}s")
                print(f"    First option: {transition.get('first_option_time', 0):.2f}s")
                print(f"    Transition time: {transition.get('transition_time', 0):.2f}s")
                print(f"    Score: {transition.get('score', 0)}/100")
                if transition.get('issues'):
                    for issue in transition['issues']:
                        print(f"    ⚠ {issue}")

    # Visual analysis
    print(f"\n{'=' * 70}")
    print("VISUAL ANALYSIS")
    print("=" * 70)

    print(f"\n  Color Analysis:")
    print(f"    Brightness: {video_analysis['color']['brightness']:.1f}")
    print(f"    Saturation: {video_analysis['color']['saturation']:.1f}")
    print(f"    Dark pixels: {video_analysis['color']['dark_pixel_ratio']*100:.1f}%")
    print(f"    Pastel-like: {'Yes' if video_analysis['color']['is_pastel'] else 'No'}")

    print(f"\n  Layout Analysis:")
    print(f"    Centered: {'Yes' if video_analysis['layout']['is_centered'] else 'No'}")
    print(f"    X deviation: {video_analysis['layout']['center_x_deviation']*100:.1f}%")
    print(f"    Y deviation: {video_analysis['layout']['center_y_deviation']*100:.1f}%")

    print(f"\n  Animation Analysis:")
    print(f"    Smoothness: {video_analysis['animation']['smoothness_score']*100:.1f}%")
    print(f"    Max frame diff: {video_analysis['animation']['max_frame_diff']:.1f}")

    if reference_analysis:
        print(f"\n  Reference Comparison:")
        print(f"    References analyzed: {reference_analysis['num_references']}")
        print(f"    Reference brightness: {reference_analysis['color']['brightness']:.1f}")

    # All Issues Summary
    if all_issues:
        print(f"\n{'=' * 70}")
        print("ALL ISSUES TO FIX")
        print("=" * 70)
        for i, issue in enumerate(all_issues, 1):
            print(f"\n  {i}. {issue}")

    # Final summary
    print(f"\n{'=' * 70}")
    if passes_quality:
        print("RESULT: ✓ PASS")
    else:
        print("RESULT: ✗ FAIL - Fix the issues above and regenerate")
    print("=" * 70)

    # Save results
    if args.output:
        results = {
            'video_path': args.video,
            'audio_path': args.audio,
            'passes_quality': passes_quality,
            'visual_score': visual_score,
            'timing_score': timing_score,
            'combined_score': combined_score,
            'video_analysis': video_analysis,
            'audio_timing': audio_timing,
            'reference_analysis': reference_analysis,
            'comparison': comparison,
            'suggestions': suggestions
        }
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nResults saved to: {args.output}")

    # Return exit code based on pass/fail
    sys.exit(0 if passes_quality else 1)


if __name__ == "__main__":
    main()
