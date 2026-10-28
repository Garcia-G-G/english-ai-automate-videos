"""Word timings with mlx-whisper on Apple Silicon, as a long-lived worker process.

Run by src/asr_timings.py under the project's Python 3.12 venv (.venv, see requirements.txt).
MLX needs Python >= 3.10 and is not thread-safe, so it lives in its own process: the panel's job
threads talk to it one at a time.

Protocol: one JSON request per stdin line {"path", "language", "model"}; one JSON reply per stdout
line {"words": [{"word", "start", "end"}, ...]} or {"error": "..."}. Standard library + mlx only.
"""

import json
import sys


def main() -> None:
    import mlx_whisper
    for line in sys.stdin:
        try:
            req = json.loads(line)
            result = mlx_whisper.transcribe(req["path"], path_or_hf_repo=req["model"],
                                            language=req.get("language"), word_timestamps=True,
                                            verbose=None)
            words = [{"word": w["word"].strip(), "start": round(float(w["start"]), 3),
                      "end": round(float(w["end"]), 3)}
                     for seg in result.get("segments") or [] for w in seg.get("words") or []
                     if str(w.get("word", "")).strip()]
            reply = {"words": words}
        except Exception as error:                          # noqa: BLE001 — one bad file never kills the worker
            reply = {"error": f"{type(error).__name__}: {error}"}
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
