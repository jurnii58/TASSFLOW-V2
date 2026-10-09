from flask import Flask
import os
from datetime import datetime, timedelta
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO

from .config import Config

# Rate Limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["300 per day", "100 per hour"],
    storage_uri="memory://"
)

# Servidor WebSocket para streaming bidireccional en tiempo real
socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Duración de sesión inactiva: 30 minutos
    app.permanent_session_lifetime = timedelta(minutes=30)
    
    # Inicializar Limiter y SocketIO
    limiter.init_app(app)
    socketio.init_app(app)

    # Inicializar eventos WebSockets
    from .sockets.telemetry_socket import init_socketio
    init_socketio(socketio)

    # Iniciar suscriptor MQTT en segundo plano
    from .core.mqtt_service import mqtt_service
    mqtt_service.start_background()

    # Context processors globales
    @app.context_processor
    def inject_globals():
        return {"now": datetime.now()}

    # Asegurar directorio de uploads
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # REGISTRO MODULAR DE BLUEPRINTS (v2.0)
    from .routes.auth import auth_bp
    from .routes.admin import admin_bp
    from .routes.usuario import usuario_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(usuario_bp)

    @app.after_request
    def add_header(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    return app