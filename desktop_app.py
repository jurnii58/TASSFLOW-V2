import os
import sys
import threading
import time
import urllib.request
import webview
from PIL import Image
import pystray

# Asegurar path base
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

ICON_PATH = os.path.join(BASE_DIR, "tassflow_app", "static", "icono.png")

# Redirigir salidas si se ejecuta con pythonw.exe sin consola
if sys.stdout is None or sys.stderr is None:
    log_file = open(os.path.join(BASE_DIR, "desktop_app.log"), "a", encoding="utf-8")
    sys.stdout = log_file
    sys.stderr = log_file

# Variables globales de control
is_exiting = False
tray_icon = None
window = None

def check_or_start_server():
    """Verifica si el servidor Flask/SocketIO está activo; si no, lo inicia automáticamente."""
    try:
        urllib.request.urlopen("http://127.0.0.1:5000/login", timeout=1.5)
        print("[OK] Servidor TASSFLOW ya en ejecución en puerto 5000.")
    except Exception:
        print("[START] Iniciando backend TASSFLOW v2.0...")
        from tassflow_app import create_app, socketio
        app = create_app()
        thread = threading.Thread(
            target=lambda: socketio.run(app, host="127.0.0.1", port=5000, debug=False, use_reloader=False, allow_unsafe_werkzeug=True),
            daemon=True
        )
        thread.start()
        time.sleep(2)

def run_background_telemetry():
    """
    Hilo de telemetría IoT continuo:
    Emite a 1 Hz bajo QoS 0 hacia Mosquitto (localhost:1883) y Gateway HTTP.
    Sigue operando permanentemente aunque la ventana esté minimizada a la bandeja del sistema.
    """
    print("[MQTT/IOT] Iniciando motor de telemetría continua (15 colaboradores, 1 Hz, QoS 0)...")
    try:
        from tassflow_app.simulator.wearable_simulator import WearableSimulator
        sim = WearableSimulator(num_usuarios=15)
        while not is_exiting:
            t0 = time.time()
            try:
                sim.emitir_tick()
            except Exception as e:
                pass
            tiempo_usado = time.time() - t0
            if tiempo_usado < 1.0:
                time.sleep(1.0 - tiempo_usado)
    except Exception as err:
        print(f"[ERROR] En loop de telemetría IoT: {err}")

def restore_window(icon=None, item=None):
    """Restaura la ventana y la trae al frente"""
    global window
    if window:
        window.show()
        window.restore()

def open_admin_panel(icon=None, item=None):
    """Navega directamente al panel administrativo y restaura la ventana"""
    global window
    if window:
        try:
            window.load_url("http://127.0.0.1:5000/admin")
        except Exception:
            pass
        window.show()
        window.restore()

def quit_application(icon=None, item=None):
    """Cierra la aplicación por completo y detiene todos los procesos"""
    global is_exiting, tray_icon, window
    is_exiting = True
    print("[EXIT] Deteniendo TASSFLOW y saliendo por completo...")
    if tray_icon:
        try:
            tray_icon.stop()
        except Exception:
            pass
    if window:
        try:
            window.destroy()
        except Exception:
            pass
    os._exit(0)

def on_closing():
    """
    Se ejecuta al hacer clic en la 'X' de la ventana.
    En lugar de terminar la aplicación, oculta la ventana en la Bandeja del Sistema (System Tray)
    para permitir que la transmisión hacia Mosquitto continúe en segundo plano.
    """
    global is_exiting, window, tray_icon
    if not is_exiting:
        if window:
            window.hide()
        if tray_icon:
            try:
                tray_icon.notify(
                    "TASSFLOW continúa ejecutándose en segundo plano y transmitiendo datos al broker Mosquitto.",
                    "TASSFLOW en Segundo Plano"
                )
            except Exception:
                pass
        return False  # Cancela el cierre/destrucción de la ventana
    return True

def setup_system_tray():
    """Configura el icono de la bandeja del sistema (System Tray) con su menú contextual"""
    global tray_icon
    try:
        img = Image.open(ICON_PATH).convert("RGBA")
        img = img.resize((64, 64), Image.Resampling.LANCZOS)
    except Exception:
        img = Image.new("RGBA", (64, 64), color=(30, 41, 59, 255))

    menu = pystray.Menu(
        pystray.MenuItem("🟢 Abrir TASSFLOW", restore_window, default=True),
        pystray.MenuItem("📊 Panel Administrativo", open_admin_panel),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("⚡ Telemetría: 15 Colaboradores (1 Hz)", None, enabled=False),
        pystray.MenuItem("📡 Broker MQTT: Mosquitto (localhost:1883)", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🛑 Salir por completo", quit_application)
    )

    tray_icon = pystray.Icon(
        "TASSFLOW",
        img,
        "TASSFLOW v2.0 - Radar Biométrico NOM-035 (En segundo plano)",
        menu
    )
    tray_icon.run_detached()

if __name__ == '__main__':
    print("=============================================================")
    print("   TASSFLOW v2.0 - Motor de Escritorio y Telemetría IoT      ")
    print("=============================================================")
    check_or_start_server()

    # Iniciar telemetría en segundo plano (Mosquitto 1 Hz QoS 0)
    telemetry_thread = threading.Thread(target=run_background_telemetry, daemon=True)
    telemetry_thread.start()

    # Configurar el icono en la bandeja del sistema de Windows
    setup_system_tray()

    # Crear ventana nativa de escritorio
    window = webview.create_window(
        title="TASSFLOW v2.0 - Radar Biométrico y Salud Ocupacional NOM-035",
        url="http://127.0.0.1:5000",
        width=1400,
        height=900,
        min_size=(960, 650),
        confirm_close=False,
        text_select=True
    )
    window.events.closing += on_closing

    print("[APP] Ventana principal iniciada. Al cerrar con 'X', continuará activa en la bandeja del sistema.")
    webview.start(private_mode=False)
