import json
import math
import time
from datetime import datetime
import threading
from bson.objectid import ObjectId
import paho.mqtt.client as mqtt

from tassflow_app.config import Config
from tassflow_app.database import telemetria_col, lineas_base_col, usuarios_col
from tassflow_app.core.ml_classifier import clasificador_biometrico
from tassflow_app.core.emergency_service import despachar_alerta
from tassflow_app.sockets.telemetry_socket import (
    emitir_telemetria_en_vivo, emitir_pausa_forzada, emitir_emergencia_critica
)

# Estado en memoria para cálculo de tiempo sedentario y throttling (1 Hz)
_estado_usuarios = {}

def procesar_lectura_telemetria(datos_payload):
    """
    Núcleo de ingesta: valida throttling a 1 Hz, clasifica contexto con IA,
    persiste en Time Series y dispara WebSockets.
    """
    try:
        # Compatibilidad con payload corto o extendido
        usuario_id = str(datos_payload.get("u") or datos_payload.get("usuario_id"))
        empresa_id = str(datos_payload.get("e") or datos_payload.get("empresa_id") or "")
        bpm = float(datos_payload.get("bpm", 72.0))
        acc = datos_payload.get("acc", [0.0, 0.0, 0.0]) # [x, y, z] en g
        
        ahora = time.time()
        
        # 1. Control de Flujo (Throttling) estricto de 1 Hz por usuario
        usuario_estado = _estado_usuarios.get(usuario_id, {
            "ultimo_ts": 0,
            "inicio_sedentario": ahora,
            "linea_base": 70.0,
            "nombre": None
        })
        
        if (ahora - usuario_estado["ultimo_ts"]) < 0.85: # Menos de ~1 seg -> descartar paquete duplicado
            return None
            
        usuario_estado["ultimo_ts"] = ahora
        
        # 2. Magnitud del vector de aceleración (|a| = sqrt(x^2 + y^2 + z^2))
        ax, ay, az = float(acc[0]), float(acc[1]), float(acc[2])
        acc_magnitude = math.sqrt(ax**2 + ay**2 + az**2)
        
        # 3. Control de tiempo sedentario
        if acc_magnitude > 0.40:
            usuario_estado["inicio_sedentario"] = ahora # Se está moviendo
            tiempo_sedentario_s = 0
        else:
            tiempo_sedentario_s = int(ahora - usuario_estado["inicio_sedentario"])
            
        # 4. Obtener línea base cardíaca (Cold Start)
        linea_base = usuario_estado.get("linea_base")
        if not linea_base or linea_base == 70.0:
            doc_lb = lineas_base_col.find_one({"usuario_id": ObjectId(usuario_id)}) if ObjectId.is_valid(usuario_id) else None
            if doc_lb and "promedio_bpm" in doc_lb:
                linea_base = float(doc_lb["promedio_bpm"])
                usuario_estado["linea_base"] = linea_base
            else:
                linea_base = 70.0
                
        delta_bpm = bpm - linea_base
        
        # 5. Obtener nombre para display
        if not usuario_estado.get("nombre"):
            u = usuarios_col.find_one({"_id": ObjectId(usuario_id)}) if ObjectId.is_valid(usuario_id) else None
            usuario_estado["nombre"] = u.get("nombre_usuario", "Colaborador") if u else "Colaborador"
            if u and not empresa_id and "empresa_id" in u:
                empresa_id = str(u["empresa_id"])
                
        _estado_usuarios[usuario_id] = usuario_estado
        
        # 6. Clasificación de Contexto (Random Forest)
        clasificacion = clasificador_biometrico.predecir(
            delta_bpm=delta_bpm,
            bpm=bpm,
            acc_magnitude=acc_magnitude,
            tiempo_sedentario_s=tiempo_sedentario_s
        )
        
        nivel = clasificacion["nivel"]
        
        # 7. Persistencia continua en MongoDB Time Series
        timestamp_actual = datetime.now()
        telemetria_doc = {
            "timestamp": timestamp_actual,
            "metadata": {
                "usuario_id": ObjectId(usuario_id) if ObjectId.is_valid(usuario_id) else usuario_id,
                "empresa_id": ObjectId(empresa_id) if ObjectId.is_valid(empresa_id) else empresa_id,
                "nombre_usuario": usuario_estado["nombre"]
            },
            "bpm": bpm,
            "delta_bpm": round(delta_bpm, 1),
            "acc_magnitude": round(acc_magnitude, 3),
            "tiempo_sedentario_s": tiempo_sedentario_s,
            "nivel_estres": nivel,
            "clasificacion": clasificacion["etiqueta"]
        }
        
        try:
            telemetria_col.insert_one(telemetria_doc)
        except Exception as e:
            pass
            
        # 8. Reacción Instantánea según Nivel
        payload_radar = {
            "usuario_id": usuario_id,
            "nombre_usuario": usuario_estado["nombre"],
            "bpm": round(bpm, 1),
            "linea_base": round(linea_base, 1),
            "acc_magnitude": round(acc_magnitude, 2),
            "tiempo_sedentario_s": tiempo_sedentario_s,
            "nivel": nivel,
            "etiqueta": clasificacion["etiqueta"],
            "descripcion": clasificacion["descripcion"],
            "color": clasificacion["color"],
            "timestamp": timestamp_actual.strftime("%H:%M:%S")
        }
        
        # Emitir al radar en vivo de la empresa
        if empresa_id:
            emitir_telemetria_en_vivo(empresa_id, payload_radar)
            
        # Alerta Nivel 2: Pausa Forzada 4-7-8 al cliente del usuario
        if nivel == 2:
            despachar_alerta(usuario_id, empresa_id, clasificacion)
            emitir_pausa_forzada(usuario_id, {
                "bpm": round(bpm, 1),
                "mensaje": "Se ha detectado estres agudo sedentario prolongado.",
                "tecnica": "4-7-8",
                "duracion_minutos": 2
            })
            
        # Alerta Nivel 3: Emergencia Crítica a brigadistas y radar
        elif nivel == 3:
            despachar_alerta(usuario_id, empresa_id, clasificacion)
            emitir_emergencia_critica(empresa_id, {
                "usuario_id": usuario_id,
                "nombre_usuario": usuario_estado["nombre"],
                "bpm": round(bpm, 1),
                "alerta": "EMERGENCIA MEDICA CRITICA: Frecuencia cardiaca extrema en reposo."
            })
            
        return payload_radar
        
    except Exception as err:
        print(f"[ERROR] Telemetria: {err}")
        return None

class MQTTService:
    """Cliente MQTT para ingesta con QoS 0 en Wi-Fi 2.4/5GHz"""
    def __init__(self, broker=Config.MQTT_BROKER, port=Config.MQTT_PORT):
        self.broker = broker
        self.port = port
        self.client = None
        self.connected = False

    def on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.connected = True
            print(f"[OK] Conectado al Broker MQTT ({self.broker}:{self.port})")
            client.subscribe(Config.MQTT_TOPIC_TELEMETRIA, qos=Config.MQTT_QOS)
        else:
            print(f"[WARN] Conexion MQTT rechazada con codigo: {rc}")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
            procesar_lectura_telemetria(payload)
        except Exception as e:
            print(f"[ERROR] Decodificando MQTT: {e}")

    def start_background(self):
        """Inicia el cliente MQTT en un hilo daemon con auto-reconexión continua"""
        def _run():
            import time
            while True:
                try:
                    if not self.connected:
                        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
                        self.client.on_connect = self.on_connect
                        self.client.on_message = self.on_message
                        self.client.connect(self.broker, self.port, keepalive=60)
                        self.client.loop_forever()
                except Exception:
                    self.connected = False
                    time.sleep(10)
                
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

mqtt_service = MQTTService()
