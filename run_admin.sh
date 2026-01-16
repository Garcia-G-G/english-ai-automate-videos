#!/bin/bash
# Launch the Admin Dashboard

cd "$(dirname "$0")"

echo "🎬 Starting English AI Videos Admin Dashboard..."
echo "   Opening http://localhost:8501"
echo ""
echo "   Press Ctrl+C to stop the server"
echo ""

# Run streamlit
/Users/go/Library/Python/3.9/bin/streamlit run src/admin.py --server.port 8501 --server.headless false
