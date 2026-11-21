"""
TASSFLOW v2.0 - Broker MQTT Nativo Oficial (Puerto 1883)
Implementación estándar del protocolo MQTT v3.1.1 en sockets TCP puros.
Captura telemetría real en tiempo real (QoS 0) a 1 Hz sin dependencias externas ni DLLs.
"""

import socket
import threading
import sys
import os

# Puerto y host estándar MQTT
HOST = "0.0.0.0"
PORT = 1883

class MQTTClientHandler(threading.Thread):
    def __init__(self, conn, addr, broker):
        super().__init__(daemon=True)
        self.conn = conn
        self.addr = addr
        self.broker = broker
        self.client_id = f"client_{addr[0]}_{addr[1]}"
        self.subscriptions = set()
        self.alive = True

    def run(self):
        try:
            while self.alive:
                header = self.conn.recv(1)
                if not header:
                    break
                packet_type = (header[0] >> 4) & 0x0F
                remaining_length = self._decode_length()
                payload = self._recv_exact(remaining_length) if remaining_length > 0 else b""

                if packet_type == 1:  # CONNECT
                    self._handle_connect(payload)
                elif packet_type == 3:  # PUBLISH
                    self._handle_publish(header[0], payload)
                elif packet_type == 8:  # SUBSCRIBE
                    self._handle_subscribe(payload)
                elif packet_type == 12:  # PINGREQ
                    # Responder con PINGRESP
                    self.conn.sendall(bytes([0xD0, 0x00]))
                elif packet_type == 14:  # DISCONNECT
                    break
        except Exception:
            pass
        finally:
            self.broker.remove_client(self)
            try:
                self.conn.close()
            except Exception:
                pass

    def _recv_exact(self, length):
        data = bytearray()
        while len(data) < length:
            chunk = self.conn.recv(length - len(data))
            if not chunk:
                break
            data.extend(chunk)
        return bytes(data)

    def _decode_length(self):
        multiplier = 1
        value = 0
        while True:
            encoded_byte = self.conn.recv(1)
            if not encoded_byte:
                return 0
            b = encoded_byte[0]
            value += (b & 127) * multiplier
            multiplier *= 128
            if (b & 128) == 0:
                break
        return value

    def _encode_length(self, length):
        encoded = bytearray()
        while True:
            digit = length % 128
            length //= 128
            if length > 0:
                digit |= 0x80
            encoded.append(digit)
            if length == 0:
                break
        return bytes(encoded)

    def _handle_connect(self, payload):
        # CONNACK: Retornar conexión aceptada (0x20, 0x02, 0x00, 0x00)
        self.conn.sendall(bytes([0x20, 0x02, 0x00, 0x00]))

    def _handle_subscribe(self, payload):
        if len(payload) < 2:
            return
        packet_id = payload[:2]
        idx = 2
        granted_qos = []
        while idx < len(payload):
            if idx + 2 > len(payload):
                break
            topic_len = (payload[idx] << 8) | payload[idx + 1]
            idx += 2
            topic = payload[idx:idx + topic_len].decode('utf-8', errors='ignore')
            idx += topic_len
            qos = payload[idx] if idx < len(payload) else 0
            idx += 1
            self.subscriptions.add(topic)
            granted_qos.append(qos)

        # SUBACK: 0x90, length, packet_id (2 bytes), granted_qos...
        suback_payload = packet_id + bytes(granted_qos)
        suback = bytes([0x90]) + self._encode_length(len(suback_payload)) + suback_payload
        self.conn.sendall(suback)

    def _handle_publish(self, header_byte, payload):
        qos = (header_byte >> 1) & 0x03
        if len(payload) < 2:
            return
        topic_len = (payload[0] << 8) | payload[1]
        topic = payload[2:2 + topic_len].decode('utf-8', errors='ignore')
        msg_idx = 2 + topic_len
        if qos > 0:
            packet_id = payload[msg_idx:msg_idx + 2]
            msg_idx += 2
            # Responder con PUBACK si es QoS 1
            if qos == 1:
                self.conn.sendall(bytes([0x40, 0x02]) + packet_id)

        msg_bytes = payload[msg_idx:]
        self.broker.broadcast(topic, msg_bytes)

    def matches(self, sub_topic, pub_topic):
        # Coincidencia estándar MQTT (+ y #)
        sub_parts = sub_topic.split('/')
        pub_parts = pub_topic.split('/')

        for i, part in enumerate(sub_parts):
            if part == '#':
                return True
            if i >= len(pub_parts):
                return False
            if part != '+' and part != pub_parts[i]:
                return False
        return len(sub_parts) == len(pub_parts)

    def send_publish(self, topic, payload):
        try:
            topic_bytes = topic.encode('utf-8')
            var_header = bytes([len(topic_bytes) >> 8, len(topic_bytes) & 0xFF]) + topic_bytes
            total_len = len(var_header) + len(payload)
            packet = bytes([0x30]) + self._encode_length(total_len) + var_header + payload
            self.conn.sendall(packet)
        except Exception:
            self.alive = False


class TassflowMQTTBroker:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.clients = []
        self.lock = threading.Lock()
        self.running = False
        self.sock = None

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(100)
        self.running = True
        print(f"[OK] [BROKER MQTT TASSFLOW] Servidor de telemetria escuchando en {self.host}:{self.port}")
        print("[OK] Protocolo MQTT v3.1.1 activo listo para capturar wearables y terminales reales.")

        while self.running:
            try:
                conn, addr = self.sock.accept()
                handler = MQTTClientHandler(conn, addr, self)
                with self.lock:
                    self.clients.append(handler)
                handler.start()
            except Exception:
                break

    def broadcast(self, topic, payload):
        with self.lock:
            for client in list(self.clients):
                for sub in client.subscriptions:
                    if client.matches(sub, topic):
                        client.send_publish(topic, payload)
                        break

    def remove_client(self, client):
        with self.lock:
            if client in self.clients:
                self.clients.remove(client)

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass


if __name__ == "__main__":
    broker = TassflowMQTTBroker()
    try:
        broker.start()
    except KeyboardInterrupt:
        print("\n[STOP] Broker MQTT detenido.")
        broker.stop()
