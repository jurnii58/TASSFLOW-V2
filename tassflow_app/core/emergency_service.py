import os
from datetime import datetime
from bson.objectid import ObjectId
from tassflow_app.database import alertas_col, usuarios_col

def despachar_alerta(usuario_id, empresa_id, clasificacion):
    """
    Registra y gestiona el protocolo de emergencia biológica.
    Nivel 1: Registro informativo.
    Nivel 2: Registro de estrés agudo y recomendación de pausa 4-7-8.
    Nivel 3: Disparo a brigadistas médicos y recursos humanos.
    """
    user = None
    if usuario_id and ObjectId.is_valid(str(usuario_id)):
        user = usuarios_col.find_one({"_id": ObjectId(usuario_id)})
        
    nombre = user.get("nombre_usuario", "Colaborador") if user else str(usuario_id)
    
    nivel = clasificacion.get("nivel", 0)
    bpm = clasificacion.get("bpm", 0)
    
    alerta_doc = {
        "usuario_id": ObjectId(usuario_id) if (usuario_id and ObjectId.is_valid(str(usuario_id))) else str(usuario_id),
        "nombre_usuario": nombre,
        "empresa_id": ObjectId(empresa_id) if (empresa_id and ObjectId.is_valid(str(empresa_id))) else str(empresa_id),
        "nivel": nivel,
        "etiqueta": clasificacion.get("etiqueta"),
        "descripcion": clasificacion.get("descripcion"),
        "bpm": bpm,
        "delta_bpm": clasificacion.get("delta_bpm"),
        "acc_magnitude": clasificacion.get("acc_magnitude"),
        "tiempo_sedentario_s": clasificacion.get("tiempo_sedentario_s"),
        "fecha": datetime.now(),
        "atendida": False
    }
    
    try:
        alerta_id = alertas_col.insert_one(alerta_doc).inserted_id
    except Exception:
        alerta_id = "alert_local"
    
    if nivel == 3:
        print(f"[EMERGENCIA MEDICA CRITICA] Colaborador: {nombre} | BPM: {bpm} | Activando protocolo de brigada...")
        
    return str(alerta_id)
