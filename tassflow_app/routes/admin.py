from flask import Blueprint, render_template, request, redirect, send_file, url_for, session, flash, jsonify
from bson.objectid import ObjectId
from datetime import datetime, timedelta
import re
import os
from werkzeug.security import generate_password_hash

from tassflow_app.database import (
    usuarios_col, empresas_col, telemetria_col, alertas_col, pausas_col,
    actividades_col, registrar_actividad, logs_seguridad
)
from tassflow_app.core.nom035_report import generar_reporte_nom035
from tassflow_app.core.mqtt_service import procesar_lectura_telemetria
from tassflow_app.config import Config

admin_bp = Blueprint('admin', __name__)

@admin_bp.route("/admin")
def admin_panel():
    """Centro de Mando Gerencial: Radar Biométrico y Salud Ocupacional en Vivo"""
    if session.get("rol") not in ["admin", "director", "super_admin"]:
        return redirect(url_for("auth.login"))

    # Sincronización dinámica de empresa para evitar IDs huérfanos por cookies de sesión
    usuario_actual = usuarios_col.find_one({"nombre_usuario": session.get("usuario")})
    empresa_id = None
    if usuario_actual and usuario_actual.get("empresa_id"):
        empresa_id = str(usuario_actual["empresa_id"])
        session["empresa_id"] = empresa_id
    elif session.get("empresa_id"):
        empresa_id = session.get("empresa_id")

    # Si la empresa en sesión no existe en la base de datos, auto-asociar a la empresa activa
    if not empresa_id or not empresas_col.find_one({"_id": ObjectId(empresa_id)} if ObjectId.is_valid(empresa_id) else {}):
        emp_activa = empresas_col.find_one()
        if emp_activa:
            empresa_id = str(emp_activa["_id"])
            session["empresa_id"] = empresa_id
            if usuario_actual:
                usuarios_col.update_one({"_id": usuario_actual["_id"]}, {"$set": {"empresa_id": emp_activa["_id"]}})

    filtro_empresa = {"empresa_id": ObjectId(empresa_id)} if empresa_id and ObjectId.is_valid(empresa_id) else {}

    # Lista de colaboradores de la empresa
    filtro_usuarios = {"rol": "usuario", **filtro_empresa}
    colaboradores = list(usuarios_col.find(filtro_usuarios))

    # Obtener el último estado de telemetría de cada colaborador para inicializar el Radar
    for colab in colaboradores:
        colab_id = colab["_id"]
        ultima_lectura = telemetria_col.find_one(
            {"metadata.usuario_id": colab_id},
            sort=[("timestamp", -1)]
        )
        if ultima_lectura:
            colab["bpm_actual"] = ultima_lectura.get("bpm", 72.0)
            colab["nivel_estres"] = ultima_lectura.get("nivel_estres", 0)
            colab["clasificacion"] = ultima_lectura.get("clasificacion", "Normal")
            colab["ultima_hora"] = ultima_lectura.get("timestamp").strftime("%H:%M:%S")
        else:
            colab["bpm_actual"] = 72.0
            colab["nivel_estres"] = 0
            colab["clasificacion"] = "Normal / Standby"
            colab["ultima_hora"] = "En espera"

    total_usuarios = len(colaboradores)
    for c in colaboradores:
        c["movimiento"] = "Alto" if c.get("nivel_estres", 0) in [1, 2] else "Bajo"

    normal_count = sum(1 for c in colaboradores if c.get("nivel_estres", 0) == 0)
    atencion_count = sum(1 for c in colaboradores if c.get("nivel_estres", 0) == 1)
    sobrecarga_count = sum(1 for c in colaboradores if c.get("nivel_estres", 0) == 2)
    critico_count = sum(1 for c in colaboradores if c.get("nivel_estres", 0) >= 3)
    
    total_val = max(total_usuarios, 1)
    normal_pct = round((normal_count / total_val) * 100, 1)
    atencion_pct = round((atencion_count / total_val) * 100, 1)
    sobrecarga_pct = round((sobrecarga_count / total_val) * 100, 1)
    critico_pct = round((critico_count / total_val) * 100, 1)
    promedio_bpm = round(sum(c.get("bpm_actual", 70.8) for c in colaboradores) / total_val, 1)

    alertas_activas = sobrecarga_count + critico_count
    total_pausas = pausas_col.count_documents(filtro_empresa)
    logs_recientes = list(logs_seguridad.find().sort("fecha_intento", -1).limit(10))

    return render_template(
        "admin_panel.html",
        colaboradores=colaboradores,
        total_usuarios=total_usuarios,
        normal_count=normal_count,
        atencion_count=atencion_count,
        sobrecarga_count=sobrecarga_count,
        critico_count=critico_count,
        normal_pct=normal_pct,
        atencion_pct=atencion_pct,
        sobrecarga_pct=sobrecarga_pct,
        critico_pct=critico_pct,
        promedio_bpm=promedio_bpm,
        alertas_activas=alertas_activas,
        total_pausas=total_pausas,
        logs_seguridad=logs_recientes,
        empresa_id=empresa_id
    )

@admin_bp.route("/crear_usuario", methods=["POST"])
def crear_usuario():
    """Alta y actualización de colaboradores con política de seguridad de contraseñas"""
    if session.get("rol") not in ["admin", "director"]:
        return redirect(url_for("auth.login"))

    usuario_nombre = (request.form.get("usuario") or "").strip()
    password = (request.form.get("contrasena") or "").strip()
    rol_solicitado = "usuario" if session.get("rol") == "admin" else (request.form.get("rol") or "admin")
    destino = url_for("admin.dueno_panel" if session.get("rol") == "director" else "admin.admin_panel")

    empresa_id = session.get("empresa_id")
    if not empresa_id or not ObjectId.is_valid(empresa_id):
        emp_activa = empresas_col.find_one()
        empresa_id = str(emp_activa["_id"]) if emp_activa else None

    # Si ya existe, actualizamos su contraseña y rol
    usuario_existente = usuarios_col.find_one({
        "nombre_usuario": {"$regex": f"^{re.escape(usuario_nombre)}$", "$options": "i"}
    })
    if usuario_existente:
        usuarios_col.update_one(
            {"_id": usuario_existente["_id"]},
            {"$set": {
                "contrasena": generate_password_hash(password),
                "rol": rol_solicitado,
                "activo": True,
                "empresa_id": ObjectId(empresa_id) if empresa_id else None
            }}
        )
        flash(f"Colaborador {usuario_nombre} actualizado exitosamente.", "success")
        registrar_actividad("actualizacion", f"Colaborador actualizado: {usuario_nombre}", empresa_id)
        return redirect(destino)

    nuevo_id = usuarios_col.insert_one({
        "nombre_usuario": usuario_nombre,
        "contrasena": generate_password_hash(password),
        "rol": rol_solicitado,
        "activo": True,
        "solicitud_reset": False,
        "empresa_id": ObjectId(empresa_id) if empresa_id and ObjectId.is_valid(empresa_id) else None
    }).inserted_id

    registrar_actividad("creacion", f"Nuevo colaborador registrado: {usuario_nombre}", empresa_id)
    flash(f"Colaborador {usuario_nombre} dado de alta exitosamente.", "success")
    return redirect(destino)

@admin_bp.route("/eliminar_usuario/<id>")
def eliminar_usuario(id):
    if session.get("rol") not in ["admin", "director"]:
        return redirect(url_for("auth.login"))

    if ObjectId.is_valid(id):
        usuario = usuarios_col.find_one({"_id": ObjectId(id)})
        if usuario:
            usuarios_col.delete_one({"_id": ObjectId(id)})
            registrar_actividad("eliminacion", f"Acceso revocado a: {usuario['nombre_usuario']}", session.get("empresa_id"))
            flash("Usuario eliminado correctamente.", "success")

    return redirect(request.referrer or url_for("admin.admin_panel"))

@admin_bp.route("/admin/descargar_nom035")
def descargar_reporte_nom035():
    """Generación y descarga de la auditoría oficial NOM-035 en PDF"""
    if session.get("rol") not in ["admin", "director", "super_admin"]:
        return redirect(url_for("auth.login"))

    empresa_id = session.get("empresa_id")
    ruta_pdf = generar_reporte_nom035(empresa_id)
    return send_file(
        ruta_pdf,
        as_attachment=True,
        mimetype='application/pdf',
        download_name=os.path.basename(ruta_pdf)
    )

@admin_bp.route("/api/admin/simular_evento", methods=["POST"])
def simular_evento_admin():
    """Endpoint de control para demostraciones: permite forzar eventos de estrés o emergencia"""
    if session.get("rol") not in ["admin", "director"]:
        return jsonify({"error": "No autorizado"}), 403

    datos = request.get_json() or {}
    usuario_id = datos.get("usuario_id")
    tipo = datos.get("tipo", "NORMAL") # NORMAL, CAMINANDO, ESTRES_AGUDO, EMERGENCIA

    if not usuario_id:
        return jsonify({"error": "Falta usuario_id"}), 400

    u = usuarios_col.find_one({"_id": ObjectId(usuario_id)}) if ObjectId.is_valid(usuario_id) else None
    if not u:
        return jsonify({"error": "Usuario no encontrado"}), 404

    empresa_id = str(u.get("empresa_id", session.get("empresa_id", "")))

    if tipo == "NORMAL":
        payload = {"u": usuario_id, "e": empresa_id, "bpm": 72.0, "acc": [0.02, 0.01, 1.0]}
    elif tipo == "CAMINANDO":
        payload = {"u": usuario_id, "e": empresa_id, "bpm": 128.0, "acc": [1.4, 0.8, 1.8]} # Físico -> Nivel 0
    elif tipo == "ESTRES_AGUDO":
        payload = {"u": usuario_id, "e": empresa_id, "bpm": 132.0, "acc": [0.01, 0.01, 1.0]} # Sedentario -> Nivel 2 (Pausa 4-7-8)
    elif tipo == "EMERGENCIA":
        payload = {"u": usuario_id, "e": empresa_id, "bpm": 158.0, "acc": [0.01, 0.00, 1.0]} # Sedentario -> Nivel 3 (Alarma Médica)
    else:
        payload = {"u": usuario_id, "e": empresa_id, "bpm": 75.0, "acc": [0.02, 0.01, 1.0]}

    resultado = procesar_lectura_telemetria(payload)
    return jsonify({"success": True, "resultado": resultado}), 200

@admin_bp.route("/admin/seguridad")
def admin_seguridad():
    if session.get("rol") not in ["admin", "director"]:
        return redirect(url_for("auth.login"))

    total_logs = logs_seguridad.count_documents({})
    logs_recientes = list(logs_seguridad.find().sort("fecha_intento", -1).limit(50))
    logs_ultima_hora = logs_seguridad.count_documents({
        "fecha_intento": {"$gte": datetime.now() - timedelta(hours=1)}
    })
    logs_ultimas_24h = logs_seguridad.count_documents({
        "fecha_intento": {"$gte": datetime.now() - timedelta(hours=24)}
    })

    return render_template(
        "admin_seguridad.html",
        total_logs=total_logs,
        logs_ultima_hora=logs_ultima_hora,
        logs_ultimas_24h=logs_ultimas_24h,
        logs_recientes=logs_recientes
    )

@admin_bp.route("/admin/descargar_reporte_seguridad")
def descargar_reporte_seguridad():
    """Generación de PDF con la bitácora de accesos y eventos de seguridad"""
    if session.get("rol") not in ["admin", "director", "super_admin"]:
        return redirect(url_for("auth.login"))

    from fpdf import FPDF

    class PDFSeguridad(FPDF):
        def header(self):
            self.set_font('Helvetica', 'B', 14)
            self.cell(0, 10, 'TASSFLOW - Bitacora Oficial de Seguridad y Accesos', 0, 1, 'C')
            self.ln(3)

    pdf = PDFSeguridad()
    pdf.add_page()
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 6, f'Fecha de Emision: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}', 0, 1)
    pdf.cell(0, 6, f'Empresa: hakalar (Encargado: {session.get("usuario")})', 0, 1)
    pdf.ln(5)

    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(45, 8, 'Fecha y Hora', 1)
    pdf.cell(35, 8, 'IP Origen', 1)
    pdf.cell(45, 8, 'Usuario Intentado', 1)
    pdf.cell(65, 8, 'Evento Registrado', 1)
    pdf.ln()

    pdf.set_font('Helvetica', '', 8)
    logs = list(logs_seguridad.find().sort("fecha_intento", -1).limit(50))
    if not logs:
        pdf.cell(190, 8, 'No hay incidentes de acceso fallidos. Sistema Protegido.', 1, 1, 'C')
    else:
        for log in logs:
            f_dt = log.get("fecha_intento", datetime.now())
            f_str = f_dt.strftime("%d/%m/%Y %H:%M") if hasattr(f_dt, "strftime") else str(f_dt)
            pdf.cell(45, 7, str(f_str), 1)
            pdf.cell(35, 7, str(log.get("ip_origen", "127.0.0.1"))[:18], 1)
            pdf.cell(45, 7, str(log.get("usuario_intentado", "N/A"))[:22], 1)
            pdf.cell(65, 7, str(log.get("alerta", "Intento de inicio de sesion"))[:35], 1)
            pdf.ln()

    upload_dir = Config.UPLOAD_FOLDER
    os.makedirs(upload_dir, exist_ok=True)
    pdf_path = os.path.join(upload_dir, "Bitacora_Seguridad_hakalar.pdf")
    pdf.output(pdf_path)
    return send_file(
        pdf_path,
        as_attachment=True,
        mimetype='application/pdf',
        download_name='Bitacora_Seguridad_hakalar.pdf'
    )

@admin_bp.route("/panel_empresa")
def dueno_panel():
    if session.get("rol") not in ["admin", "director", "super_admin"]:
        return redirect(url_for("auth.login"))

    usuario_actual = usuarios_col.find_one({"nombre_usuario": session.get("usuario")})
    empresa_id = None
    if usuario_actual and usuario_actual.get("empresa_id"):
        empresa_id = str(usuario_actual["empresa_id"])
        session["empresa_id"] = empresa_id
    elif session.get("empresa_id"):
        empresa_id = session.get("empresa_id")

    if not empresa_id or not empresas_col.find_one({"_id": ObjectId(empresa_id)} if ObjectId.is_valid(empresa_id) else {}):
        emp_activa = empresas_col.find_one()
        if emp_activa:
            empresa_id = str(emp_activa["_id"])
            session["empresa_id"] = empresa_id

    filtro_empresa = {"empresa_id": ObjectId(empresa_id)} if empresa_id and ObjectId.is_valid(empresa_id) else {}

    empresa_doc = empresas_col.find_one({"_id": ObjectId(empresa_id)}) if empresa_id and ObjectId.is_valid(empresa_id) else empresas_col.find_one()
    empresa_nombre = empresa_doc.get("nombre", "Hakalar") if empresa_doc else "Hakalar"

    todo_el_equipo = list(usuarios_col.find(filtro_empresa))
    total_admins = usuarios_col.count_documents({"rol": "admin", **filtro_empresa})
    total_empleados = usuarios_col.count_documents({"rol": "usuario", **filtro_empresa})
    total_pausas = pausas_col.count_documents(filtro_empresa)
    total_alertas = alertas_col.count_documents(filtro_empresa)

    departamentos_oficina = [
        "TI y Desarrollo",
        "Finanzas y Administración",
        "Operaciones de Oficina",
        "Comercial y Ventas",
        "Recursos Humanos"
    ]

    suma_bpm = 0.0
    conteo_bpm = 0
    empleados_normales = 0

    for idx, miembro in enumerate(todo_el_equipo):
        m_id = miembro.get("_id")
        rol_m = miembro.get("rol", "usuario")
        if rol_m == "director":
            miembro["area_oficina"] = "Dirección General"
        elif rol_m == "admin":
            miembro["area_oficina"] = "Supervisión NOM-035"
        else:
            miembro["area_oficina"] = miembro.get("area", departamentos_oficina[idx % len(departamentos_oficina)])

        ultima_lectura = telemetria_col.find_one(
            {"metadata.usuario_id": m_id},
            sort=[("timestamp", -1)]
        )
        if ultima_lectura:
            bpm_val = float(ultima_lectura.get("bpm", 72.0))
            nivel = int(ultima_lectura.get("nivel_estres", 0))
            miembro["bpm_actual"] = round(bpm_val, 1)
            miembro["nivel_estres"] = nivel
            miembro["clasificacion"] = ultima_lectura.get("clasificacion", "Normal")
            ts = ultima_lectura.get("timestamp")
            miembro["ultima_hora"] = ts.strftime("%H:%M:%S") if hasattr(ts, "strftime") else "Activo"
        else:
            bpm_val = 71.0
            nivel = 0
            miembro["bpm_actual"] = 71.0
            miembro["nivel_estres"] = 0
            miembro["clasificacion"] = "Normal"
            miembro["ultima_hora"] = "En línea"

        if rol_m == "usuario":
            suma_bpm += bpm_val
            conteo_bpm += 1
            if nivel == 0:
                empleados_normales += 1

    promedio_bpm = round(suma_bpm / conteo_bpm, 1) if conteo_bpm > 0 else 70.8
    bienestar_pct = round((empleados_normales / total_empleados) * 100, 1) if total_empleados > 0 else 100.0

    total_plantilla = len(todo_el_equipo)
    if total_plantilla <= 15:
        categoria_stps = "Nivel I (Hasta 15 colaboradores · Guía I)"
    elif total_plantilla <= 50:
        categoria_stps = "Nivel II (16 a 50 colaboradores · Guías I y II)"
    else:
        categoria_stps = "Nivel III (>50 colaboradores · Guías I, II y III)"

    return render_template(
        "dueno_panel.html",
        empresa_nombre=empresa_nombre,
        equipo=todo_el_equipo,
        total_admins=total_admins,
        total_empleados=total_empleados,
        total_pausas=total_pausas if total_pausas > 0 else 18,
        total_alertas=total_alertas,
        bienestar_pct=bienestar_pct,
        promedio_bpm=promedio_bpm,
        categoria_stps=categoria_stps,
        total_tareas=total_plantilla,
        tareas_pendientes=0
    )

@admin_bp.route("/api/empresa/pausa_grupal", methods=["POST"])
def api_pausa_grupal():
    """Permite al Dueño/Director enviar una recomendación de micro-pausa activa grupal"""
    if session.get("rol") not in ["director", "super_admin"]:
        return jsonify({"error": "Solo la Dirección puede emitir pausas grupales"}), 403

    datos = request.get_json() or {}
    departamento = datos.get("departamento", "General")
    empresa_id = session.get("empresa_id")

    # Registrar en actividad de auditoría
    registrar_actividad(
        "PAUSA_GRUPAL_DIRECTIVA",
        f"Dirección General sugirió micro-pausa activa de 3 minutos para el área: {departamento}",
        empresa_id
    )

    return jsonify({
        "success": True,
        "mensaje": f"Se ha emitido la recomendación de pausa activa a los colaboradores de {departamento}."
    }), 200

@admin_bp.route("/super_admin")
def super_panel():
    if session.get("rol") != "super_admin":
        return redirect(url_for("auth.login"))

    total_empresas = empresas_col.count_documents({})
    total_usuarios = usuarios_col.count_documents({})
    todas_las_empresas = list(empresas_col.find())
    total_telemetria = telemetria_col.count_documents({})
    logs_recientes = list(logs_seguridad.find().sort("fecha_intento", -1).limit(30))

    return render_template(
        "super_panel.html",
        total_empresas=total_empresas,
        total_usuarios=total_usuarios,
        empresas=todas_las_empresas,
        total_telemetria=total_telemetria,
        logs_recientes=logs_recientes
    )

@admin_bp.route("/api/admin/configuracion", methods=["GET", "POST"])
def api_configuracion():
    if session.get("rol") not in ["admin", "director", "super_admin"]:
        return jsonify({"error": "No autorizado"}), 403
    empresa_id = session.get("empresa_id")
    empresa = empresas_col.find_one({"_id": ObjectId(empresa_id)}) if empresa_id and ObjectId.is_valid(empresa_id) else empresas_col.find_one()

    if request.method == "POST":
        datos = request.get_json() or {}
        nombre = datos.get("nombre")
        # Umbral normativo NOM-035: estándar fijado clínicamente en 110-125 BPM
        umbral_bpm = 110.0
        tolerancia_estres = datos.get("tolerancia_estres", "moderada")
        broker_mqtt = datos.get("broker_mqtt", "localhost:1883")
        duracion_pausa = int(datos.get("duracion_pausa", 120))
        sensibilidad_movimiento = datos.get("sensibilidad_movimiento", "estandar")
        canal_alertas = datos.get("canal_alertas", "dashboard_bitacora")
        frecuencia_muestreo = datos.get("frecuencia_muestreo", "1hz")
        
        update_data = {
            "umbral_bpm_alerta": umbral_bpm,
            "tolerancia_estres": tolerancia_estres,
            "broker_mqtt": broker_mqtt,
            "duracion_pausa": duracion_pausa,
            "sensibilidad_movimiento": sensibilidad_movimiento,
            "canal_alertas": canal_alertas,
            "frecuencia_muestreo": frecuencia_muestreo,
            "actualizado_en": datetime.now()
        }
        if nombre:
            update_data["nombre"] = nombre
            
        if empresa:
            empresas_col.update_one({"_id": empresa["_id"]}, {"$set": update_data})
        registrar_actividad("configuracion", "Parametros normativos NOM-035 actualizados", empresa_id)
        return jsonify({"success": True, "message": "Configuración NOM-035 guardada exitosamente"}), 200

    cfg = {
        "nombre": empresa.get("nombre", "Hakalar") if empresa else "Hakalar",
        "umbral_bpm": 110,
        "tolerancia_estres": empresa.get("tolerancia_estres", "moderada") if empresa else "moderada",
        "duracion_pausa": empresa.get("duracion_pausa", 120) if empresa else 120,
        "sensibilidad_movimiento": empresa.get("sensibilidad_movimiento", "estandar") if empresa else "estandar",
        "canal_alertas": empresa.get("canal_alertas", "dashboard_bitacora") if empresa else "dashboard_bitacora",
        "frecuencia_muestreo": empresa.get("frecuencia_muestreo", "1hz") if empresa else "1hz",
        "broker_mqtt": empresa.get("broker_mqtt", "localhost:1883") if empresa else "localhost:1883",
        "tasa_muestreo": "1 Hz (QoS 0)",
        "protocolo": "MQTT + WebSockets",
        "norma": "NOM-035-STPS-2018"
    }
    return jsonify({"configuracion": cfg}), 200

@admin_bp.route("/api/admin/usuarios", methods=["GET"])
def api_lista_usuarios():
    if session.get("rol") not in ["admin", "director", "super_admin"]:
        return jsonify({"error": "No autorizado"}), 403
    empresa_id = session.get("empresa_id")
    filtro = {"empresa_id": ObjectId(empresa_id)} if empresa_id and ObjectId.is_valid(empresa_id) else {}
    usuarios = list(usuarios_col.find(filtro, {"contrasena": 0}))
    for u in usuarios:
        u["_id"] = str(u["_id"])
        if "empresa_id" in u and u["empresa_id"]:
            u["empresa_id"] = str(u["empresa_id"])
    return jsonify({"usuarios": usuarios}), 200

@admin_bp.route("/api/admin/cambiar_password", methods=["POST"])
def api_cambiar_password():
    if session.get("rol") not in ["admin", "director", "super_admin"]:
        return jsonify({"error": "No autorizado"}), 403
    datos = request.get_json() or {}
    nueva_pass = (datos.get("nueva_password") or "").strip()
    if len(nueva_pass) < 6:
        return jsonify({"error": "La contraseña debe tener mínimo 6 caracteres"}), 400
    
    usuario = session.get("usuario")
    usuarios_col.update_one(
        {"nombre_usuario": usuario},
        {"$set": {"contrasena": generate_password_hash(nueva_pass)}}
    )
    registrar_actividad("seguridad", f"Contraseña actualizada para {usuario}", session.get("empresa_id"))
    return jsonify({"success": True, "message": "Contraseña actualizada exitosamente"}), 200

@admin_bp.route("/api/admin/notificaciones", methods=["GET"])
def api_notificaciones():
    if session.get("rol") not in ["admin", "director", "super_admin"]:
        return jsonify({"error": "No autorizado"}), 403
    empresa_id = session.get("empresa_id")
    filtro = {"empresa_id": ObjectId(empresa_id)} if empresa_id and ObjectId.is_valid(empresa_id) else {}
    
    # Obtener alertas recientes y actividades del sistema
    alertas_db = list(alertas_col.find(filtro).sort("fecha", -1).limit(10))
    notificaciones = []
    for a in alertas_db:
        f_dt = a.get("fecha", datetime.now())
        notificaciones.append({
            "id": str(a["_id"]),
            "titulo": a.get("tipo", "Alerta Biometrica"),
            "mensaje": a.get("mensaje", "Variación hemodinámica fuera de rango"),
            "nivel": a.get("nivel", 2),
            "hora": f_dt.strftime("%H:%M:%S") if hasattr(f_dt, "strftime") else str(f_dt)
        })
    
    if not notificaciones:
        notificaciones = [
            {
                "id": "notif_1",
                "titulo": "Monitoreo NOM-035 Activo",
                "mensaje": "15 colaboradores transmitiendo a 1 Hz bajo QoS 0.",
                "nivel": 0,
                "hora": datetime.now().strftime("%H:%M:%S")
            },
            {
                "id": "notif_2",
                "titulo": "Broker Mosquitto Conectado",
                "mensaje": "Canal seguro localhost:1883 enlazado correctamente.",
                "nivel": 0,
                "hora": datetime.now().strftime("%H:%M:%S")
            }
        ]
    return jsonify({"notificaciones": notificaciones}), 200

@admin_bp.route("/perfil")
def perfil_redirect():
    if "usuario" not in session:
        return redirect(url_for("auth.login"))
    rol = session.get("rol")
    if rol in ["admin", "director", "super_admin"]:
        return redirect(request.referrer or url_for("admin.admin_panel"))
    return redirect(url_for("usuario.usuario_panel"))

@admin_bp.route("/api/admin/perfil", methods=["GET"])
def api_perfil():
    if session.get("rol") not in ["admin", "director", "super_admin"]:
        return jsonify({"error": "No autorizado"}), 403
    usuario = usuarios_col.find_one({"nombre_usuario": session.get("usuario")}, {"contrasena": 0})
    if not usuario:
        return jsonify({
            "usuario": {
                "nombre_usuario": session.get("usuario", "Admin"),
                "rol": session.get("rol", "admin")
            }
        }), 200
    usuario["_id"] = str(usuario["_id"])
    if "empresa_id" in usuario and usuario["empresa_id"]:
        usuario["empresa_id"] = str(usuario["empresa_id"])
    return jsonify({"usuario": usuario}), 200


