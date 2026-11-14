#!/bin/bash
# Panel 2.0 (STEP 85 §7): the API, /media and the built app on http://localhost:8501, the usual URL
# The old Streamlit panel moved to 8502 (run_admin.sh); both read the same files.

cd "$(dirname "$0")" || exit 1
PORT=8501

PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python

if ! "$PY" -c "import fastapi, uvicorn" 2>/dev/null; then
    echo "Faltan fastapi y uvicorn en $PY. Instálalos con: $PY -m pip install -r requirements.txt  (o: uv pip install --python $PY fastapi==0.162.7 uvicorn==0.54.0)"
    exit 1
fi

# Rebuild only when the built app is missing or older than its sources.
stale=0
if [ ! -f panel/dist/index.html ]; then
    stale=1
elif [ -n "$(find panel/src panel/index.html panel/package-lock.json panel/vite.config.ts -newer panel/dist/index.html 2>/dev/null | head -1)" ]; then
    stale=1
fi
if [ "$stale" = 1 ]; then
    if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
        echo "Hace falta Node.js y npm para compilar el panel nuevo y no los encuentro."
        echo "Instálalos (por ejemplo: brew install node) y vuelve a ejecutar ./run_panel.sh"
        exit 1
    fi
    echo "Compilando el panel (solo la primera vez o cuando cambia el código)..."
    (cd panel && { [ -d node_modules ] && [ node_modules -nt package-lock.json ] || npm ci; } && npm run build) || {
        echo "No se pudo compilar el panel. Revisa el error de arriba."
        exit 1
    }
fi

if lsof -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
    echo "El puerto $PORT ya está en uso: probablemente el panel ya está abierto en http://127.0.0.1:$PORT"
    exit 1
fi

echo "Panel listo: http://127.0.0.1:$PORT   (Ctrl+C para parar; el panel antiguo sigue en http://localhost:8502)"
cd src && exec "../$PY" -m panel_api
