import os
import sys

# Asegurar que tassflow_app se encuentre sin importar desde que directorio se ejecute
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tassflow_app import create_app, socketio

def iniciar_broker_mqtt():
    """Inicia el Broker MQTT nativo (1883) en segundo plano si el puerto está libre"""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        res = s.connect_ex(('127.0.0.1', 1883))
        s.close()
        if res != 0:
            import threading
            from broker_mqtt import TassflowMQTTBroker
            broker = TassflowMQTTBroker(port=1883)
            hilo = threading.Thread(target=broker.start, daemon=True)
            hilo.start()
        else:
            print("[INFO] Broker MQTT ya activo en el puerto 1883.")
    except Exception as e:
        print(f"[WARN] No se pudo iniciar el Broker MQTT automatico: {e}")

iniciar_broker_mqtt()

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print(f"[START] [TASSFLOW v2.0] Servidor Telemetria y WebSockets iniciado en http://localhost:{port}")
    socketio.run(app, host="0.0.0.0", port=port, debug=True, use_reloader=False, allow_unsafe_werkzeug=True)