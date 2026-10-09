import os
import sys
from datetime import datetime
import random
from pymongo import MongoClient
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "carga_mental_db")

if not MONGO_URI:
    print("[ERROR] Variable de entorno MONGO_URI no definida en .env. Configure el archivo .env.")
    sys.exit(1)

print(f"[HAKALAR SETUP] Conectando a MongoDB ({DB_NAME})...")
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=15000)
    client.admin.command('ping')
    print("[OK] Conectado exitosamente via MONGO_URI.")
except Exception as e:
    print(f"[ERROR] No se pudo conectar a MongoDB: {e}")
    sys.exit(1)

db = client[DB_NAME]

# 1. Eliminar absolutamente todas las colecciones existentes
colecciones_existentes = db.list_collection_names()
print(f"\n[1/6] Eliminando colecciones previas: {colecciones_existentes}...")
for col_name in colecciones_existentes:
    db.drop_collection(col_name)
    print(f" - Coleccion '{col_name}' eliminada.")
print("[OK] Base de datos limpia al 100%.")

# 2. Crear Colección Time Series de Telemetría Biométrica
print("\n[2/6] Creando Colección Time Series 'telemetria_biometrica'...")
try:
    db.create_collection(
        "telemetria_biometrica",
        timeseries={
            "timeField": "timestamp",
            "metaField": "metadata",
            "granularity": "seconds"
        }
    )
    print("[OK] Colección Time Series 'telemetria_biometrica' creada.")
except Exception as e:
    print(f"[INFO] Creando indices estándar: {e}")
    db["telemetria_biometrica"].create_index([("timestamp", -1)])
    db["telemetria_biometrica"].create_index([("metadata.usuario_id", 1)])

# 3. Crear índices optimizados
print("\n[3/6] Creando índices optimizados...")
db["usuarios"].create_index([("nombre_usuario", 1)], unique=True)
db["empresas"].create_index([("nombre_empresa", 1)])
db["lineas_base_cardiacas"].create_index([("usuario_id", 1)], unique=True)
db["alertas_salud"].create_index([("empresa_id", 1), ("fecha", -1)])
db["alertas_salud"].create_index([("usuario_id", 1), ("nivel", 1)])
db["pausas_guiadas"].create_index([("usuario_id", 1), ("fecha", -1)])
db["reportes_nom035"].create_index([("empresa_id", 1), ("fecha_generacion", -1)])
db["actividades"].create_index([("empresa_id", 1), ("fecha", -1)])
db["logs_seguridad"].create_index([("fecha_intento", -1)])
print("[OK] Todos los índices creados exitosamente.")

# 4. Crear Empresa Principal 'hakalar'
print("\n[4/6] Registrando empresa principal 'hakalar'...")
empresa_id = db["empresas"].insert_one({
    "nombre_empresa": "hakalar",
    "fecha_creacion": datetime.now(),
    "estado": "Activo",
    "sector": "Tecnologia / Consultoria Integral",
    "normativa_aplicable": "NOM-035-STPS-2018",
    "descripcion": "Empresa hakalar - Implementacion Piloto TASSFLOW v2.0"
}).inserted_id
print(f"[OK] Empresa 'hakalar' creada con ID: {empresa_id}")

# 5. Crear Encargado y Usuarios de Gestión para 'hakalar'
print("\n[5/6] Creando encargado y administradores de 'hakalar'...")
usuarios_gestion = [
    {
        "nombre_usuario": "jurnii",
        "nombre_completo": "Jurnii (Encargado / Director General)",
        "contrasena": generate_password_hash("jurnii123"),
        "rol": "director",
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
    },
    {
        "nombre_usuario": "luis",
        "nombre_completo": "Luis (Gerente Operativo)",
        "contrasena": generate_password_hash("luis123"),
        "rol": "admin",
        "activo": True,
        "empresa_id": empresa_id
    }
]

for ug in usuarios_gestion:
    db["usuarios"].insert_one(ug)
    print(f" [OK] Encargado/Gestion registrado: {ug['nombre_usuario']} ({ug['rol']}) -> Empresa: hakalar")

# 6. Crear los 15 Colaboradores del Piloto asignados a 'hakalar'
print("\n[6/6] Creando 15 colaboradores del piloto asignados a 'hakalar'...")
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
    uid = db["usuarios"].insert_one({
        "nombre_usuario": uname,
        "nombre_completo": nombre,
        "contrasena": generate_password_hash("usuario123"),
        "rol": "usuario",
        "activo": True,
        "empresa_id": empresa_id
    }).inserted_id

    # Registrar línea base cardíaca individualizada
    db["lineas_base_cardiacas"].insert_one({
        "usuario_id": uid,
        "empresa_id": empresa_id,
        "promedio_bpm": lb_bpm,
        "fecha_calibracion": datetime.now(),
        "calibrado": True,
        "metodo": "Calibracion Basal TASSFLOW v2.0"
    })

    # Sembrar lectura inicial de telemetría para que el radar se active de inmediato
    db["telemetria_biometrica"].insert_one({
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
    print(f" - Colaborador: {uname.ljust(15)} | {nombre.ljust(18)} | Base: {lb_bpm} BPM -> Asignado a hakalar")

# Bitácora de Auditoría
db["actividades"].insert_one({
    "tipo": "INICIALIZACION_HAKALAR",
    "mensaje": f"Empresa 'hakalar' inicializada con encargado 'jurnii' y 15 colaboradores biométricos.",
    "empresa_id": empresa_id,
    "fecha": datetime.now()
})

print("\n" + "="*70)
print("[EXITO TOTAL] EMPRESA 'hakalar' CONFIGURADA EXITOSAMENTE EN MONGODB ATLAS")
print(f"Empresa ID: {empresa_id}")
print(f"Encargado Principal: jurnii (director)")
print(f"Total colaboradores asignados a hakalar: {db.usuarios.count_documents({'rol': 'usuario', 'empresa_id': empresa_id})}")
print(f"Colecciones activas: {db.list_collection_names()}")
print("="*70)
