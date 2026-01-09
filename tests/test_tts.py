#!/usr/bin/env python3
"""
Unit tests for the TTS module.
Tests Spanish content with English words for teaching.
"""

import asyncio
import json
import os
import sys
import tempfile
import unittest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tts import text_to_speech, list_voices, RECOMMENDED_VOICES, DEFAULT_VOICE, DEFAULT_RATE


class TestTTS(unittest.TestCase):
    """Test cases for the TTS module."""

    def test_text_to_speech_spanish(self):
        """Test TTS with Spanish content teaching English."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test.mp3")
            # Spanish content with English word
            text = "¿Sabías que 'embarrassed' NO significa 'embarazada'?"

            timestamps = asyncio.run(text_to_speech(text, output_path))

            # Check audio file was created
            self.assertTrue(os.path.exists(output_path))
            self.assertGreater(os.path.getsize(output_path), 0)

            # Check JSON file was created
            json_path = output_path.rsplit(".", 1)[0] + ".json"
            self.assertTrue(os.path.exists(json_path))

            # Check timestamps structure
            self.assertIn("duration", timestamps)
            self.assertIn("words", timestamps)
            self.assertIsInstance(timestamps["words"], list)
            self.assertGreater(len(timestamps["words"]), 0)

    def test_word_timestamps_structure(self):
        """Test that word timestamps have correct structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test.mp3")
            text = "Hola, hoy aprenderemos phrasal verbs."

            timestamps = asyncio.run(text_to_speech(text, output_path))

            # Check word structure
            for word in timestamps["words"]:
                self.assertIn("word", word)
                self.assertIn("start", word)
                self.assertIn("end", word)
                self.assertGreaterEqual(word["end"], word["start"])

    def test_rate_adjustment(self):
        """Test that rate adjustment works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_slow = os.path.join(tmpdir, "slow.mp3")
            output_fast = os.path.join(tmpdir, "fast.mp3")
            text = "Esta es una prueba de velocidad."

            ts_slow = asyncio.run(text_to_speech(text, output_slow, rate="+0%"))
            ts_fast = asyncio.run(text_to_speech(text, output_fast, rate="+25%"))

            # Faster rate should have shorter duration
            self.assertLess(ts_fast["duration"], ts_slow["duration"])

    def test_list_voices(self):
        """Test listing available voices."""
        voices = asyncio.run(list_voices())
        self.assertIsInstance(voices, list)
        self.assertGreater(len(voices), 0)

    def test_list_spanish_voices(self):
        """Test listing Spanish voices."""
        voices = asyncio.run(list_voices("es"))
        self.assertIsInstance(voices, list)
        self.assertGreater(len(voices), 0)
        for voice in voices:
            self.assertTrue(voice["Locale"].startswith("es"))

    def test_default_voice_is_spanish(self):
        """Test that default voice is Spanish (for Spanish content)."""
        self.assertTrue(DEFAULT_VOICE.startswith("es-"))

    def test_recommended_voices_exist(self):
        """Test that recommended voices are valid."""
        all_voices = asyncio.run(list_voices())
        voice_names = [v["ShortName"] for v in all_voices]

        for recommended in RECOMMENDED_VOICES.keys():
            self.assertIn(
                recommended, voice_names,
                f"Recommended voice {recommended} not found"
            )


class TestFalseFriendsContent(unittest.TestCase):
    """Test with real false friends content."""

    def test_embarrassed_example(self):
        """Test the embarrassed/embarazada example."""
        text = """¿Sabías que 'embarrassed' NO significa 'embarazada'?
Muchos hispanohablantes cometen este error.
En inglés, embarrassed significa sentirse avergonzado.
Por ejemplo: I was so embarrassed when I forgot her name.
La traducción correcta de embarazada es pregnant.
¡Recuerda este falso amigo!"""

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "embarrassed.mp3")

            timestamps = asyncio.run(text_to_speech(text, output_path))

            # Should have many words
            self.assertGreater(len(timestamps["words"]), 30)

            # Duration should be reasonable
            self.assertGreater(timestamps["duration"], 5.0)

            # File should be reasonable size
            file_size = os.path.getsize(output_path)
            self.assertGreater(file_size, 20000)

            print(f"\nEmbarrassed example results:")
            print(f"  Duration: {timestamps['duration']:.2f} seconds")
            print(f"  Words: {len(timestamps['words'])}")
            print(f"  File size: {file_size / 1024:.1f} KB")


if __name__ == "__main__":
    unittest.main(verbosity=2)
