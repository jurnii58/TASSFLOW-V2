import os
import sys

# Asegurar que tassflow_app se encuentre sin importar desde que directorio se ejecute
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tassflow_app import create_app, socketio

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print(f"[START] [TASSFLOW v2.0] Servidor Telemetria y WebSockets iniciado en http://localhost:{port}")
    socketio.run(app, host="0.0.0.0", port=port, debug=True, use_reloader=False, allow_unsafe_werkzeug=True)