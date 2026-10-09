from flask import request
from flask_socketio import emit, join_room, leave_room
from datetime import datetime
from bson.objectid import ObjectId
from tassflow_app.database import pausas_col, alertas_col, usuarios_col

socketio_instance = None

def init_socketio(socketio):
    global socketio_instance
    socketio_instance = socketio

    @socketio.on('connect')
    def handle_connect():
        pass

    @socketio.on('join_empresa')
    def handle_join_empresa(data):
        empresa_id = data.get('empresa_id')
        if empresa_id:
            join_room(f"empresa_{empresa_id}")

    @socketio.on('join_usuario')
    def handle_join_usuario(data):
        usuario_id = data.get('usuario_id')
        if usuario_id:
            join_room(f"usuario_{usuario_id}")

    @socketio.on('pausa_completada')
    def handle_pausa_completada(data):
        """Registra la culminación exitosa de la técnica de respiración 4-7-8 para NOM-035"""
        usuario_id = data.get('usuario_id')
        empresa_id = data.get('empresa_id')
        duracion_segundos = data.get('duracion_segundos', 120)
        bpm_inicial = data.get('bpm_inicial')
        bpm_final = data.get('bpm_final')
        
        if usuario_id:
            user = usuarios_col.find_one({"_id": ObjectId(usuario_id)})
            pausas_col.insert_one({
                "usuario_id": ObjectId(usuario_id),
                "nombre_usuario": user.get("nombre_usuario", "Desconocido") if user else "Desconocido",
                "empresa_id": ObjectId(empresa_id) if empresa_id else None,
                "tecnica": "Respiracion 4-7-8 (Inhala 4s, Sosten 7s, Exhala 8s)",
                "duracion_segundos": duracion_segundos,
                "bpm_inicial": bpm_inicial,
                "bpm_final": bpm_final,
                "reduccion_bpm": round(bpm_inicial - bpm_final, 1) if bpm_inicial and bpm_final else None,
                "fecha": datetime.now(),
                "cumplimiento_nom035": True
            })
            
            # Notificar al radar del administrador que el empleado completó su pausa
            if empresa_id:
                emit('usuario_recuperado', {
                    "usuario_id": usuario_id,
                    "mensaje": f"{user.get('nombre_usuario', 'Empleado')} completo exitosamente su pausa 4-7-8."
                }, to=f"empresa_{empresa_id}")

def emitir_telemetria_en_vivo(empresa_id, telemetria_dict):
    """Transmite en vivo la telemetría procesada al radar administrativo vía WebSocket"""
    if socketio_instance and empresa_id:
        socketio_instance.emit('telemetria_en_vivo', telemetria_dict, to=f"empresa_{empresa_id}")

def emitir_pausa_forzada(usuario_id, datos_alerta):
    """Dispara el modal invasivo Always-on-Top en el cliente del usuario"""
    if socketio_instance and usuario_id:
        socketio_instance.emit('orden_pausa_forzada', datos_alerta, to=f"usuario_{usuario_id}")

def emitir_emergencia_critica(empresa_id, datos_emergencia):
    """Activa la alarma médica sonora y visual en el panel gerencial"""
    if socketio_instance and empresa_id:
        socketio_instance.emit('alerta_emergencia_critica', datos_emergencia, to=f"empresa_{empresa_id}")
