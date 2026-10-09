from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session
from bson.objectid import ObjectId
from datetime import datetime
from tassflow_app.database import usuarios_col, lineas_base_col, telemetria_col, pausas_col
from tassflow_app.core.mqtt_service import procesar_lectura_telemetria

usuario_bp = Blueprint('usuario', __name__)

@usuario_bp.route("/usuario")
@usuario_bp.route("/guardian")
def usuario_panel():
    """
    Panel del Guardián Invisible:
    Interfaz pasiva que no distrae al colaborador. Monitorea en segundo plano
    y solo interviene en caso de alerta Nivel 2 (Pausa 4-7-8) o Nivel 3.
    """
    if session.get("rol") != "usuario":
        return redirect(url_for("auth.login"))

    usuario_id = session.get("usuario_id")
    empresa_id = session.get("empresa_id")
    nombre_usuario = session.get("usuario")

    # Obtener línea base cardíaca del colaborador
    linea_base = 70.0
    if usuario_id and ObjectId.is_valid(usuario_id):
        doc_lb = lineas_base_col.find_one({"usuario_id": ObjectId(usuario_id)})
        if doc_lb and "promedio_bpm" in doc_lb:
            linea_base = float(doc_lb["promedio_bpm"])

    # Obtener última lectura de telemetría
    ultima_lectura = None
    if usuario_id and ObjectId.is_valid(usuario_id):
        ultima_lectura = telemetria_col.find_one(
            {"metadata.usuario_id": ObjectId(usuario_id)},
            sort=[("timestamp", -1)]
        )

    # Conteo de pausas 4-7-8 realizadas este mes
    total_pausas = pausas_col.count_documents({"usuario_id": ObjectId(usuario_id)}) if usuario_id and ObjectId.is_valid(usuario_id) else 0

    return render_template(
        "usuario_guardian.html",
        usuario_id=usuario_id,
        empresa_id=empresa_id,
        nombre_usuario=nombre_usuario,
        linea_base=round(linea_base, 1),
        bpm_actual=round(ultima_lectura["bpm"], 1) if ultima_lectura else round(linea_base, 1),
        total_pausas=total_pausas
    )

@usuario_bp.route("/api/telemetria_iot", methods=["POST"])
def recibir_telemetria_iot():
    """
    Endpoint Gateway para ingesta de Web Bluetooth o emuladores (1 Hz, QoS 0).
    Acepta el payload JSON compacto.
    """
    datos = request.get_json()
    if not datos:
        return jsonify({"success": False, "error": "Payload vacío"}), 400

    # Si la petición viene de sesión web activa y no trae usuario_id, inyectarlo
    if session.get("usuario_id") and not datos.get("u") and not datos.get("usuario_id"):
        datos["u"] = session.get("usuario_id")
        datos["e"] = session.get("empresa_id", "")

    resultado = procesar_lectura_telemetria(datos)
    if resultado is None:
        # Se descartó por throttling (< 1 seg) o error menor
        return jsonify({"success": True, "throttled": True}), 200

    return jsonify({"success": True, "clasificacion": resultado}), 200

@usuario_bp.route("/api/registrar_pausa", methods=["POST"])
def registrar_pausa():
    """Registra la culminación exitosa de una pausa guiada 4-7-8 para NOM-035"""
    if not session.get("usuario_id"):
        return jsonify({"error": "No autorizado"}), 401

    datos = request.get_json() or {}
    usuario_id = session.get("usuario_id")
    empresa_id = session.get("empresa_id")

    pausas_col.insert_one({
        "usuario_id": ObjectId(usuario_id),
        "nombre_usuario": session.get("usuario"),
        "empresa_id": ObjectId(empresa_id) if empresa_id and ObjectId.is_valid(empresa_id) else None,
        "tecnica": "Respiración 4-7-8 (Inhala 4s, Sostén 7s, Exhala 8s)",
        "duracion_segundos": datos.get("duracion_segundos", 120),
        "bpm_inicial": datos.get("bpm_inicial"),
        "bpm_final": datos.get("bpm_final"),
        "reduccion_bpm": round(float(datos.get("bpm_inicial", 0)) - float(datos.get("bpm_final", 0)), 1) if datos.get("bpm_inicial") and datos.get("bpm_final") else None,
        "fecha": datetime.now(),
        "cumplimiento_nom035": True
    })

    return jsonify({"success": True, "mensaje": "Pausa registrada en auditoría NOM-035"}), 200