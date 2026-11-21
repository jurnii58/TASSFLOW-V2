import os
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/carga_mental_db")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "carga_mental_db")

# Conexión a MongoDB Atlas o local con timeout rápido y respaldo en memoria garantizado
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000, connectTimeoutMS=3000)
    client.admin.command('ping')
    db = client[MONGO_DB_NAME]
    print(f"[OK] Conectado exitosamente a MongoDB Atlas [{MONGO_DB_NAME}]")
except Exception as e:
    import mongomock
    client = mongomock.MongoClient()
    db = client[MONGO_DB_NAME]
    print(f"[INFO] MongoDB Atlas no disponible ({e}). Base de datos de respaldo en memoria activada.")

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
    """Siembra empresa Hakalar y colaboradores del piloto para demostración inmediata"""
    try:
        from werkzeug.security import generate_password_hash

        empresa_id = empresas_col.insert_one({
            "nombre": "Hakalar",
            "nombre_empresa": "hakalar",
            "fecha_creacion": datetime.now(),
            "estado": "Activo",
            "sector": "Tecnologia / Consultoria Integral",
            "normativa_aplicable": "NOM-035-STPS-2018"
        }).inserted_id

        usuarios_gestion = [
            {
                "nombre_usuario": "jurnii",
                "nombre_completo": "Jurnii (Encargado / Director General)",
                "contrasena": generate_password_hash("Turbo57K*"),
                "rol": "director",
                "activo": True,
                "empresa_id": empresa_id
            },
            {
                "nombre_usuario": "director",
                "nombre_completo": "Director General Hakalar",
                "contrasena": generate_password_hash("director123"),
                "rol": "director",
                "activo": True,
                "empresa_id": empresa_id
            },
            {
                "nombre_usuario": "luis",
                "nombre_completo": "Luis (Gerente Operativo)",
                "contrasena": generate_password_hash("Pixel%93Q"),
                "rol": "admin",
                "activo": True,
                "empresa_id": empresa_id
            },
            {
                "nombre_usuario": "admin",
                "nombre_completo": "Administrador de Salud Ocupacional",
                "contrasena": generate_password_hash("admin123"),
                "rol": "admin",
                "activo": True,
                "empresa_id": empresa_id
            }
        ]
        for ug in usuarios_gestion:
            usuarios_col.insert_one(ug)

        COLABORADORES_PILOTO = [
            ("sara", "Sara Vazquez", 70),
            ("ana.martinez", "Ana Martinez", 68),
            ("carlos.lopez", "Carlos Lopez", 72),
            ("elena.gomez", "Elena Gomez", 67),
            ("fernando.ruiz", "Fernando Ruiz", 74),
            ("gabriela.diaz", "Gabriela Diaz", 69),
            ("hugo.morales", "Hugo Morales", 71),
            ("isabel.castro", "Isabel Castro", 68),
            ("javier.perez", "Javier Perez", 73),
            ("laura.ortiz", "Laura Ortiz", 70),
            ("manuel.silva", "Manuel Silva", 72),
            ("natalia.reyes", "Natalia Reyes", 67),
            ("oscar.torres", "Oscar Torres", 75),
            ("patricia.vega", "Patricia Vega", 69),
            ("ricardo.nunez", "Ricardo Nunez", 71)
        ]

        for uname, nombre, lb_bpm in COLABORADORES_PILOTO:
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
                "promedio_bpm": lb_bpm,
                "fecha_calibracion": datetime.now(),
                "calibrado": True
            })

            telemetria_col.insert_one({
                "timestamp": datetime.now(),
                "metadata": {
                    "usuario_id": uid,
                    "empresa_id": str(empresa_id),
                    "nombre_usuario": nombre
                },
                "bpm": float(lb_bpm),
                "acc_magnitude": 1.0,
                "nivel_estres": 0,
                "clasificacion": "Normal",
                "origen": "TASSFLOW Edge Gateway"
            })
        print(f"[OK] Empresa Hakalar y 15 colaboradores inicializados (ID: {empresa_id})")
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

# Inicializar base de datos y sembrar usuarios automáticamente al cargar
init_db()

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