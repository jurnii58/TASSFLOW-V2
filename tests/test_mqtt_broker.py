import os
import sys
import threading
import time
import paho.mqtt.client as mqtt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from broker_mqtt import TassflowMQTTBroker

broker = TassflowMQTTBroker(port=1883)
t = threading.Thread(target=broker.start, daemon=True)
t.start()
time.sleep(0.5)

recibido = []

def on_msg(client, userdata, msg):
    recibido.append(msg.payload.decode('utf-8'))

sub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
sub.on_message = on_msg
sub.connect("127.0.0.1", 1883)
sub.subscribe("tassflow/empresa/+/telemetria")
sub.loop_start()
time.sleep(0.3)

pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
pub.connect("127.0.0.1", 1883)
pub.publish("tassflow/empresa/hakalar/telemetria", '{"u": "sara", "bpm": 85.5, "sensor": "HUAWEI_BAND_REAL"}')
time.sleep(0.5)

sub.loop_stop()
broker.stop()

print("PAQUETE MQTT CAPTURADO CON EXITO:", recibido)
assert len(recibido) == 1
assert "HUAWEI_BAND_REAL" in recibido[0]
print("--- TEST PASSED: EL BROKER MQTT CAPTURA DATOS REALES EN EL PUERTO 1883 ---")
