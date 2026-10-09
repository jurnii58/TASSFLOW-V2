import os
from dotenv import load_dotenv

# Cargar las variables del archivo .env
load_dotenv()

class Config:
    # Llave secreta para las sesiones
    SECRET_KEY = os.getenv("SECRET_KEY", "tassflow_v2_telemetry_secure_key_2026")
    
    # URL de conexión a MongoDB
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/carga_mental_db")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "carga_mental_db")
    
    # Broker MQTT (Infraestructura Wi-Fi mixta 2.4/5GHz)
    MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
    MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
    MQTT_TOPIC_TELEMETRIA = "tassflow/empresa/+/telemetria"
    MQTT_QOS = 0  # At Most Once para cero overhead en Wi-Fi 2.4 GHz
    MQTT_THROTTLE_RATE_HZ = 1.0  # 1 evento/segundo por usuario
    
    # Parámetros Clínicos y NOM-035
    COLD_START_WEEKS = 3  # Periodo de calibración de línea base cardíaca
    BPM_THRESHOLD_LEVEL_1 = 100  # Atención / Fatiga moderada
    BPM_THRESHOLD_LEVEL_2 = 125  # Estrés agudo sedentario (Pausa 4-7-8)
    BPM_THRESHOLD_LEVEL_3 = 150  # Emergencia médica crítica sostenida
    
    # Directorio de reportes generados
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")