"""STEP 80 §3: how long each panel page takes to render, cold and warm.

    python3 tools/panel_timing.py [OUT.json]

Each page is run with Streamlit's AppTest (the page's own script, no browser): «cold» is the first
run of a fresh session in a fresh process-level cache state for that page, «warm» the median of
three reruns of the same session — what a click costs. Network reads are not made: the stats page
reads only its saved snapshot, and the voice balance reader is the cached one.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
PAGES = ["Dashboard", "Generate", "Queue", "Review", "Upload", "Library", "Topics", "Scheduler", "Settings",
         "Logs", "Performance"]
LABELS = {"Dashboard": "Inicio", "Generate": "Crear", "Queue": "Cola", "Review": "Revisar", "Upload": "Subir",
          "Library": "Biblioteca", "Topics": "Temas", "Scheduler": "Programar", "Settings": "Ajustes",
          "Logs": "Registros", "Performance": "Rendimiento"}


def time_page(page: str) -> dict:
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "src" / "admin.py"), default_timeout=600)
    at.session_state["current_page"] = page
    t0 = time.perf_counter()
    at.run()
    cold = time.perf_counter() - t0
    warm = []
    for _ in range(3):
        t0 = time.perf_counter()
        at.run()
        warm.append(time.perf_counter() - t0)
    errors = [str(e.value)[:120] for e in at.exception]
    return {"page": page, "label": LABELS[page], "cold_s": round(cold, 2),
            "warm_s": round(statistics.median(warm), 2), "errors": errors}


def main(argv: list) -> int:
    rows = []
    for page in PAGES:
        row = time_page(page)
        rows.append(row)
        print(f"{row['label']:<12} cold {row['cold_s']:>6.2f} s   warm {row['warm_s']:>6.2f} s"
              + (f"   ERROR {row['errors']}" if row["errors"] else ""), flush=True)
    if argv:
        Path(argv[0]).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
