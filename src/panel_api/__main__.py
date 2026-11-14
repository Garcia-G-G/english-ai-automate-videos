"""STEP 85 §7: `python -m panel_api` serves the API, /media and the built app on 127.0.0.1:8501 (run_panel.sh calls this)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402

from panel_api.app import HOST, PORT, app  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning", access_log=False)
