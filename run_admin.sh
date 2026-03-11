#!/bin/bash
# Launch the Admin Dashboard

cd "$(dirname "$0")"

echo "Starting English AI Videos Admin Dashboard..."
echo "   Opening http://localhost:8501"
echo ""
echo "   Press Ctrl+C to stop the server"
echo ""

# Try streamlit from common locations
if command -v streamlit &> /dev/null; then
    streamlit run src/admin.py --server.port 8501 --server.headless false
elif python3 -m streamlit --version &> /dev/null; then
    python3 -m streamlit run src/admin.py --server.port 8501 --server.headless false
elif [ -f "/Users/go/Library/Python/3.9/bin/streamlit" ]; then
    /Users/go/Library/Python/3.9/bin/streamlit run src/admin.py --server.port 8501 --server.headless false
else
    echo "ERROR: streamlit not found. Install with: pip3 install streamlit"
    exit 1
fi
