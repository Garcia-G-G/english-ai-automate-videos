"""ElevenLabs TTS provider — wraps tts_elevenlabs.py.

Now with humanized speech: natural pauses, per-segment speed,
bilingual pronunciation hints, and breathing/emphasis markers.
"""

import logging
from typing import Dict

from tts_base import TTSProvider

logger = logging.getLogger(__name__)


class ElevenLabsTTSProvider(TTSProvider):
    name = "elevenlabs"

    def __init__(self, voice_id: str = None):
        from tts_elevenlabs import DEFAULT_VOICE_ID
        self.voice_id = voice_id or DEFAULT_VOICE_ID

    def generate_from_script(self, script_data: Dict, output_path: str, **kwargs) -> Dict:
        from tts_elevenlabs import (
            generate_quiz_audio_segmented,
            generate_fill_blank_audio_segmented,
            generate_true_false_audio_segmented,
            generate_vocabulary_audio_segmented,
            generate_segment_audio,
        )
        from tts_common import extract_english_words_from_script

        voice_id = kwargs.get('voice_id', self.voice_id)
        video_type = script_data.get('type', 'educational')

        if video_type == 'quiz':
            result = generate_quiz_audio_segmented(
                script=script_data, output_path=output_path, voice_id=voice_id,
            )
        elif video_type == 'fill_blank':
            result = generate_fill_blank_audio_segmented(
                script=script_data, output_path=output_path, voice_id=voice_id,
            )
        elif video_type == 'true_false':
            result = generate_true_false_audio_segmented(
                script=script_data, output_path=output_path, voice_id=voice_id,
            )
        elif video_type == 'vocabulary':
            result = generate_vocabulary_audio_segmented(
                script=script_data, output_path=output_path, voice_id=voice_id,
            )
        else:
            # educational, pronunciation — single TTS call
            text = script_data.get('full_script', '')
            if not text:
                raise ValueError("Script missing 'full_script' field")

            from tts_common import clean_for_tts
            tts_text = clean_for_tts(text)

            english_words = extract_english_words_from_script(script_data)

            duration = generate_segment_audio(
                tts_text, output_path, voice_id=voice_id,
                segment_type='explanation',
                english_words=english_words,
            )
            english_phrases = script_data.get('english_phrases', [])

            # --- Get REAL word timestamps from Whisper ---
            whisper_words = []
            try:
                from tts_openai import extract_timestamps_whisper
                logger.info("Extracting real word timestamps with Whisper...")
                whisper_result = extract_timestamps_whisper(
                    output_path,
                    original_text=text,
                    explicit_english=english_phrases,
                )
                whisper_words = whisper_result.get('words', [])
                whisper_duration = whisper_result.get('duration', duration)
                if whisper_words:
                    duration = whisper_duration
                    logger.info("Whisper: got %d real word timestamps", len(whisper_words))
                else:
                    logger.warning("Whisper returned no words, falling back to estimation")
            except Exception as e:
                logger.warning("Whisper failed (%s), falling back to character estimation", e)

            if whisper_words:
                from video.educational import add_sentence_boundaries
                words_with_segments = add_sentence_boundaries(whisper_words, text)

                segments = []
                current_seg_id = None
                seg_words = []
                for w in words_with_segments:
                    sid = w.get('segment_id', 0)
                    if sid != current_seg_id:
                        if seg_words:
                            segments.append({
                                'start': seg_words[0]['start'],
                                'end': seg_words[-1]['end'],
                                'text': ' '.join(sw['word'] for sw in seg_words),
                            })
                        seg_words = [w]
                        current_seg_id = sid
                    else:
                        seg_words.append(w)
                if seg_words:
                    segments.append({
                        'start': seg_words[0]['start'],
                        'end': seg_words[-1]['end'],
                        'text': ' '.join(sw['word'] for sw in seg_words),
                    })

                result = {
                    'duration': duration,
                    'words': words_with_segments,
                    'segments': segments,
                }
            else:
                from tts_elevenlabs import estimate_word_timestamps
                est_words, est_segments = estimate_word_timestamps(text, duration, english_phrases)
                result = {'duration': duration, 'words': est_words, 'segments': est_segments}

            self.copy_script_metadata(script_data, result)

        self.save_json(output_path, result)
        return result

    def generate_audio(self, text: str, output_path: str, **kwargs) -> Dict:
        from tts_elevenlabs import generate_segment_audio

        voice_id = kwargs.get('voice_id', self.voice_id)
        segment_type = kwargs.get('segment_type', 'default')
        english_words = kwargs.get('english_words', None)

        duration = generate_segment_audio(
            text, output_path, voice_id=voice_id,
            segment_type=segment_type,
            english_words=english_words,
        )
        return {'duration': duration, 'words': []}
