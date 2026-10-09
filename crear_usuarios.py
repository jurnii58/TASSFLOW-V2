import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import datetime
import random
from werkzeug.security import generate_password_hash
from tassflow_app.database import usuarios_col, empresas_col, lineas_base_col, db
from bson import ObjectId

print("[TASSFLOW v2.0] Sincronizando entorno de telemetria con base de datos...")

try:
    # 1. Obtener o registrar empresa principal
    empresa = empresas_col.find_one()
    if not empresa:
        empresa_id = empresas_col.insert_one({
            "nombre_empresa": "hyperion",
            "fecha_creacion": datetime.now(),
            "estado": "Activo",
            "sector": "Tecnologia / Consultoria",
            "normativa_aplicable": "NOM-035-STPS-2018"
        }).inserted_id
        nombre_empresa = "hyperion"
        print(f"[OK] Empresa creada con ID: {empresa_id}")
    else:
        empresa_id = empresa["_id"]
        nombre_empresa = empresa.get("nombre_empresa", "hyperion")
        print(f"[OK] Empresa existente detectada: '{nombre_empresa}' (ID: {empresa_id})")

    # 2. Asegurar línea base cardíaca para usuarios existentes
    for u in usuarios_col.find({"empresa_id": empresa_id}):
        u_id = u["_id"]
        existe_lb = lineas_base_col.find_one({"usuario_id": u_id})
        if not existe_lb:
            lineas_base_col.insert_one({
                "usuario_id": u_id,
                "empresa_id": empresa_id,
                "promedio_bpm": random.randint(68, 74),
                "fecha_calibracion": datetime.now(),
                "calibrado": True
            })
            print(f"[OK] Linea base calibrada para usuario existente: {u.get('nombre_usuario')}")

    # 3. Completar los 15 colaboradores del piloto si faltan
    NOMBRES_COLABORADORES = [
        "Ana Martinez", "Carlos Lopez", "Elena Gomez", "Fernando Ruiz",
        "Gabriela Diaz", "Hugo Morales", "Isabel Castro", "Javier Perez",
        "Laura Ortiz", "Manuel Silva", "Natalia Reyes", "Oscar Torres",
        "Patricia Vega", "Ricardo Nunez", "Sofia Medina"
    ]

    colaboradores_actuales = usuarios_col.count_documents({"rol": "usuario", "empresa_id": empresa_id})
    faltantes = max(0, 15 - colaboradores_actuales)

    if faltantes > 0:
        print(f"[INFO] Creando {faltantes} colaboradores adicionales para completar el piloto de 15...")
        for i in range(1, faltantes + 1):
            uname = f"colaborador_{i:02d}"
            nombre = NOMBRES_COLABORADORES[(i - 1) % len(NOMBRES_COLABORADORES)]
            if not usuarios_col.find_one({"nombre_usuario": uname}):
                uid = usuarios_col.insert_one({
                    "nombre_usuario": uname,
                    "nombre_completo": nombre,
                    "contrasena": generate_password_hash("usuario123"),
                    "rol": "usuario",
                    "activo": True,
                    "empresa_id": empresa_id
                }).inserted_id

                lineas_base_col.insert_one({
                    "usuario_id": uid,
                    "empresa_id": empresa_id,
                    "promedio_bpm": random.randint(66, 74),
                    "fecha_calibracion": datetime.now(),
                    "calibrado": True
                })

    total_piloto = usuarios_col.count_documents({"rol": "usuario", "empresa_id": empresa_id})
    print(f"[OK] Total de colaboradores activos en el piloto ({nombre_empresa}): {total_piloto}")
    print("[OK] Sincronizacion completada exitosamente.")
except Exception as e:
    print(f"[ERROR] Error al sincronizar con MongoDB: {e}")