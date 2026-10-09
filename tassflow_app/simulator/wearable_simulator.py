import time
import json
import random
import math
import urllib.request
import paho.mqtt.client as mqtt
from datetime import datetime

BROKER = "localhost"
PORT = 1883
TOPIC_BASE = "tassflow/empresa"
NUM_COLABORADORES = 15

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Perfiles de los 15 colaboradores del piloto
NOMBRES_COLABORADORES = [
    "Ana Martinez", "Carlos Lopez", "Elena Gomez", "Fernando Ruiz",
    "Gabriela Diaz", "Hugo Morales", "Isabel Castro", "Javier Perez",
    "Laura Ortiz", "Manuel Silva", "Natalia Reyes", "Oscar Torres",
    "Patricia Vega", "Ricardo Nunez", "Sofia Medina"
]

class WearableSimulator:
    def __init__(self, num_usuarios=NUM_COLABORADORES, empresa_id=None):
        self.num_usuarios = num_usuarios
        
        # Conectar con la empresa activa de MongoDB Atlas (ej. hyperion)
        if not empresa_id:
            try:
                from tassflow_app.database import empresas_col
                emp = empresas_col.find_one()
                if emp:
                    empresa_id = str(emp["_id"])
            except Exception:
                pass
        self.empresa_id = empresa_id or "69c1f95517238430142984fb"
        self.mqtt_client = None
        self.mqtt_activo = False
        self.dispositivos = []
        self._inicializar_dispositivos()
        self._conectar_mqtt()

    def _inicializar_dispositivos(self):
        colaboradores_db = []
        try:
            from tassflow_app.database import usuarios_col
            from bson import ObjectId
            filtro = {"rol": "usuario"}
            if ObjectId.is_valid(self.empresa_id):
                filtro["empresa_id"] = ObjectId(self.empresa_id)
            for u in usuarios_col.find(filtro).limit(self.num_usuarios):
                colaboradores_db.append(u)
        except Exception:
            pass

        for i in range(self.num_usuarios):
            if i < len(colaboradores_db):
                u_doc = colaboradores_db[i]
                u_id = str(u_doc["_id"])
                nombre = u_doc.get("nombre_completo") or u_doc.get("nombre_usuario", f"Colaborador {i+1}")
            else:
                u_id = f"usr_{i+1:02d}"
                nombre = NOMBRES_COLABORADORES[i % len(NOMBRES_COLABORADORES)]

            linea_base = random.randint(65, 75)
            self.dispositivos.append({
                "id": u_id,
                "nombre": nombre,
                "linea_base": linea_base,
                "bpm": float(linea_base),
                "estado_fisiologico": "NORMAL_SEDENTARIO",
                "tiempo_estado": 0
            })

    def _conectar_mqtt(self):
        try:
            self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            self.mqtt_client.connect(BROKER, PORT, keepalive=60)
            self.mqtt_client.loop_start()
            self.mqtt_activo = True
            print(f"[OK] [Simulador IoT] Conectado a broker MQTT {BROKER}:{PORT}")
        except Exception:
            self.mqtt_activo = False
            print("[INFO] [Simulador IoT] Broker MQTT no accesible. Modo Gateway HTTP directo activado.")

    def set_estado_usuario(self, usuario_index, estado):
        """Permite forzar un estado en un colaborador específico para pruebas de estrés"""
        if 0 <= usuario_index < len(self.dispositivos):
            self.dispositivos[usuario_index]["estado_fisiologico"] = estado
            self.dispositivos[usuario_index]["tiempo_estado"] = 0
            print(f"[EVENTO] Colaborador {self.dispositivos[usuario_index]['nombre']} cambio a estado: {estado}")

    def generar_lectura_1hz(self, disp):
        """
        Genera 1 lectura por segundo (1 Hz) respetando acelerometría y BPM según su estado.
        """
        estado = disp["estado_fisiologico"]
        base = disp["linea_base"]
        disp["tiempo_estado"] += 1

        if estado == "NORMAL_SEDENTARIO":
            bpm = base + random.uniform(-3, 5)
            acc = [
                random.uniform(-0.05, 0.05),
                random.uniform(-0.04, 0.04),
                random.uniform(0.98, 1.02)
            ]
        elif estado == "CAMINANDO":
            # Esfuerzo físico (subir escaleras / caminar) -> BPM alto + aceleración alta
            bpm = base + random.uniform(35, 55)
            acc = [
                random.uniform(-1.2, 1.2),
                random.uniform(-0.8, 0.8),
                random.uniform(0.5, 2.3)
            ]
        elif estado == "ESTRES_AGUDO":
            # Nivel 2: Taquicardia severa sin movimiento físico (estrés cognitivo)
            bpm = base + random.uniform(45, 65) # 115 - 140 BPM
            acc = [
                random.uniform(-0.02, 0.02),
                random.uniform(-0.02, 0.02),
                random.uniform(0.99, 1.01)
            ]
        elif estado == "EMERGENCIA":
            # Nivel 3: Crisis médica extrema (>150 BPM estático)
            bpm = 158 + random.uniform(-2, 10)
            acc = [0.01, 0.01, 1.00]
        else:
            bpm = base
            acc = [0.0, 0.0, 1.0]

        disp["bpm"] = bpm
        
        # Payload JSON ultra-compacto (QoS 0, 1 Hz)
        return {
            "u": disp["id"],
            "e": self.empresa_id,
            "nombre": disp["nombre"],
            "bpm": round(bpm, 1),
            "acc": [round(a, 3) for a in acc],
            "ts": int(time.time())
        }

    def emitir_tick(self, http_gateway_url="http://localhost:5000/api/telemetria_iot"):
        """Emite un ciclo de 1 segundo para los 15 colaboradores bajo QoS 0"""
        # Reintentar conexión con broker Mosquitto periódicamente si no estaba activo
        if not self.mqtt_activo:
            ahora = time.time()
            if not hasattr(self, "_ultimo_reintento_mqtt") or (ahora - self._ultimo_reintento_mqtt > 8):
                self._ultimo_reintento_mqtt = ahora
                self._conectar_mqtt()

        for disp in self.dispositivos:
            payload = self.generar_lectura_1hz(disp)
            
            # 1. Enviar por MQTT si está activo (QoS 0 estricto hacia Mosquitto)
            if self.mqtt_activo:
                try:
                    topic = f"{TOPIC_BASE}/{self.empresa_id}/telemetria"
                    self.mqtt_client.publish(topic, json.dumps(payload), qos=0)
                except Exception:
                    self.mqtt_activo = False
            # 2. Respaldo por HTTP Gateway hacia Flask si Mosquitto no está levantado
            if not self.mqtt_activo:
                try:
                    data_bytes = json.dumps(payload).encode('utf-8')
                    req = urllib.request.Request(
                        http_gateway_url,
                        data=data_bytes,
                        headers={'Content-Type': 'application/json'},
                        method='POST'
                    )
                    with urllib.request.urlopen(req, timeout=0.4) as response:
                        pass
                except Exception:
                    pass

    def run_simulacion_continua(self, segundos=60):
        print(f"[START] Iniciando simulacion de {self.num_usuarios} colaboradores a 1 Hz bajo MQTT QoS 0...")
        inicio = time.time()
        iteracion = 0
        try:
            while (time.time() - inicio) < segundos:
                t0 = time.time()
                iteracion += 1
                
                # Cada ciclo simular variaciones de estrés
                if iteracion == 5:
                    self.set_estado_usuario(2, "CAMINANDO")      # Elena camina (Físico -> Nivel 0)
                    self.set_estado_usuario(7, "ESTRES_AGUDO")  # Javier sufre estrés agudo (Nivel 2 -> Pausa 4-7-8)
                if iteracion == 12:
                    self.set_estado_usuario(11, "EMERGENCIA")   # Oscar sufre arritmia extrema (Nivel 3 -> Alerta Médica)
                    
                self.emitir_tick()
                
                tiempo_usado = time.time() - t0
                if tiempo_usado < 1.0:
                    time.sleep(1.0 - tiempo_usado)
        except KeyboardInterrupt:
            print("\n[STOP] Simulacion detenida.")

if __name__ == "__main__":
    simulador = WearableSimulator(num_usuarios=15)
    simulador.run_simulacion_continua(segundos=30)
