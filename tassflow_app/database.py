import os
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/carga_mental_db")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "carga_mental_db")

# Conexión a MongoDB Atlas o local con timeout adaptado para cloud replica sets y reintento
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=15000, connectTimeoutMS=15000)
    client.admin.command('ping')
    db = client[MONGO_DB_NAME]
    print(f"[OK] Conectado exitosamente a MongoDB Atlas [{MONGO_DB_NAME}]")
except Exception as e:
    try:
        import time
        time.sleep(1.0)
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=20000, connectTimeoutMS=20000)
        client.admin.command('ping')
        db = client[MONGO_DB_NAME]
        print(f"[OK] Conectado exitosamente a MongoDB Atlas [{MONGO_DB_NAME}] (en reintento)")
    except Exception as e2:
        import mongomock
        client = mongomock.MongoClient()
        db = client[MONGO_DB_NAME]
        print(f"[INFO] MongoDB Atlas no disponible ({e2}). Base de datos de respaldo en memoria activada.")

_db_initialized = False

def init_db():
    """Inicializa esquemas, Time Series e indices si no existen"""
    global _db_initialized
    if _db_initialized:
        return
    try:
        colecciones_existentes = db.list_collection_names()
        
        # 1. Colección Time Series de Telemetría Biométrica
        if "telemetria_biometrica" not in colecciones_existentes:
            try:
                db.create_collection(
                    "telemetria_biometrica",
                    timeseries={
                        "timeField": "timestamp",
                        "metaField": "metadata",
                        "granularity": "seconds"
                    }
                )
                print("[OK] Coleccion Time Series 'telemetria_biometrica' creada.")
            except Exception:
                db["telemetria_biometrica"].create_index([("timestamp", -1)])
                db["telemetria_biometrica"].create_index([("metadata.usuario_id", 1)])
                print("[INFO] Indices de telemetria optimizados aplicados.")
                
        # 2. Índices de optimización
        db["alertas_salud"].create_index([("empresa_id", 1), ("fecha", -1)])
        db["alertas_salud"].create_index([("usuario_id", 1), ("nivel", 1)])
        db["lineas_base_cardiacas"].create_index([("usuario_id", 1)])
        db["pausas_guiadas"].create_index([("usuario_id", 1), ("fecha", -1)])
        db["usuarios"].create_index([("nombre_usuario", 1)])
        db["empresas"].create_index([("nombre_empresa", 1)])
    except Exception:
        pass

    # 3. Auto-siembra de colaboradores del piloto si está vacía
    try:
        if usuarios_col.count_documents({}) == 0:
            sembrar_datos_piloto()
    except Exception:
        pass

    _db_initialized = True

def sembrar_datos_piloto():
    """Siembra empresa y colaboradores para demostración inmediata"""
    try:
        import random
        from werkzeug.security import generate_password_hash

        empresa_id = empresas_col.insert_one({
            "nombre_empresa": "TechCorp Health & Safety",
            "fecha_creacion": datetime.now(),
            "estado": "Activo",
            "sector": "Tecnologia / Consultoria",
            "normativa_aplicable": "NOM-035-STPS-2018"
        }).inserted_id

        usuarios_col.insert_one({
            "nombre_usuario": "director",
            "nombre_completo": "Director General",
            "contrasena": generate_password_hash("director123"),
            "rol": "director",
            "activo": True,
            "empresa_id": empresa_id
        })

        usuarios_col.insert_one({
            "nombre_usuario": "admin",
            "nombre_completo": "Administrador de Salud Ocupacional",
            "contrasena": generate_password_hash("admin123"),
            "rol": "admin",
            "activo": True,
            "empresa_id": empresa_id
        })

        NOMBRES_COLABORADORES = [
            "Ana Martinez", "Carlos Lopez", "Elena Gomez", "Fernando Ruiz",
            "Gabriela Diaz", "Hugo Morales", "Isabel Castro", "Javier Perez",
            "Laura Ortiz", "Manuel Silva", "Natalia Reyes", "Oscar Torres",
            "Patricia Vega", "Ricardo Nunez", "Sofia Medina"
        ]

        for i, nombre in enumerate(NOMBRES_COLABORADORES, start=1):
            uname = f"empleado{i:02d}"
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
        print(f"[OK] 15 colaboradores del piloto inicializados con empresa_id: {empresa_id}")
    except Exception as e:
        print(f"[WARN] Error en sembrado inicial: {e}")

# Colecciones exportables
usuarios_col = db["usuarios"]
empresas_col = db["empresas"]
telemetria_col = db["telemetria_biometrica"]
alertas_col = db["alertas_salud"]
lineas_base_col = db["lineas_base_cardiacas"]
pausas_col = db["pausas_guiadas"]
reportes_nom035_col = db["reportes_nom035"]
actividades_col = db["actividades"]
logs_seguridad = db["logs_seguridad"]

def registrar_actividad(tipo, mensaje, empresa_id=None):
    """Registra auditoría administrativa con multi-tenancy"""
    try:
        actividades_col.insert_one({
            "tipo": tipo,
            "mensaje": mensaje,
            "empresa_id": empresa_id,
            "fecha": datetime.now()
        })
    except Exception:
        pass