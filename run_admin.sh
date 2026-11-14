#!/bin/bash
# Launch the Admin Dashboard

cd "$(dirname "$0")"

echo "Starting English AI Videos Admin Dashboard..."
echo "   Opening http://localhost:8501"
echo ""
echo "   Press Ctrl+C to stop the server"
echo ""

# The project venv (Python 3.12, pinned to the same packages; see requirements.txt) when it
# exists: 3-15 % less CPU per frame than the system 3.9, which no longer gets security fixes.
if [ -x .venv/bin/python ]; then
    exec .venv/bin/python -m streamlit run src/admin.py --server.port 8501 --server.headless false
fi

# Streamlit falls back to polling every source file 5x/second without watchdog
# (its own startup message says so). Free and open source; offer it once.
if ! python3 -c "import watchdog" &> /dev/null; then
    echo "   Tip: 'python3 -m pip install --user watchdog' makes the dashboard lighter."
    echo ""
fi

# Try streamlit from common locations
if command -v streamlit &> /dev/null; then
    streamlit run src/admin.py --server.port 8501 --server.headless false
elif python3 -m streamlit --version &> /dev/null; then
    python3 -m streamlit run src/admin.py --server.port 8501 --server.headless false
elif [ -x "$(python3 -m site --user-base 2>/dev/null)/bin/streamlit" ]; then
    "$(python3 -m site --user-base)/bin/streamlit" run src/admin.py --server.port 8501 --server.headless false
else
    echo "ERROR: streamlit not found. Install with: pip3 install streamlit"
    exit 1
fi
