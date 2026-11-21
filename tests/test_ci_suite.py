"""
Suite de Pruebas Automatizadas para Pipeline CI/CD - TASSFLOW v2.0
Valida:
1. Inicialización Flask + SocketIO y rutas principales (/login, /sw.js, /api/telemetria_iot)
2. Clasificador Random Forest (Nivel 0 Reposo/Físico, Nivel 1 Atención, Nivel 2 Estrés Agudo, Nivel 3 Emergencia)
3. Generador de Expediente Técnico PDF NOM-035-STPS-2018
4. Archivos de infraestructura Docker (Dockerfile y docker-compose.yml)
"""

import os
import sys

# Asegurar que el directorio raíz esté en sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from tassflow_app import create_app
from tassflow_app.core.ml_classifier import clasificador_biometrico
from tassflow_app.core.nom035_report import generar_reporte_nom035


def test_flask_app_and_service_worker():
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    # 1. Login page
    resp_login = client.get("/login")
    assert resp_login.status_code == 200

    # 2. Service Worker Web Push endpoint
    resp_sw = client.get("/sw.js")
    assert resp_sw.status_code == 200
    assert resp_sw.headers.get("Service-Worker-Allowed") == "/"
    assert b"SHOW_NATIVE_NOTIFICATION" in resp_sw.data


def test_random_forest_classifier_levels():
    # Nivel 0: Estado basal en escritorio (72 BPM, sedentario)
    res_basal = clasificador_biometrico.predecir(delta_bpm=2.0, bpm=72.0, acc_magnitude=1.01, tiempo_sedentario_s=120)
    assert res_basal["nivel"] == 0

    # Nivel 0: Esfuerzo físico motriz (130 BPM pero caminando con acc_dinamica >= 0.40g) -> Cero falsos positivos
    res_fisico = clasificador_biometrico.predecir(delta_bpm=55.0, bpm=130.0, acc_magnitude=1.55, tiempo_sedentario_s=0)
    assert res_fisico["nivel"] == 0

    # Nivel 1: Fatiga moderada / Atención en pantalla (96 BPM en reposo)
    res_atencion = clasificador_biometrico.predecir(delta_bpm=22.0, bpm=96.0, acc_magnitude=1.02, tiempo_sedentario_s=600)
    assert res_atencion["nivel"] == 1

    # Nivel 2: Estrés agudo sedentario (125 BPM frente a monitor sin movimiento) -> Dispara pausa 4-7-8
    res_estres = clasificador_biometrico.predecir(delta_bpm=45.0, bpm=125.0, acc_magnitude=1.01, tiempo_sedentario_s=900)
    assert res_estres["nivel"] == 2
    assert res_estres["accion"] == "PAUSA_FORZADA_478"

    # Nivel 3: Emergencia crítica (>150 BPM en reposo absoluto)
    res_emergencia = clasificador_biometrico.predecir(delta_bpm=80.0, bpm=158.0, acc_magnitude=1.00, tiempo_sedentario_s=1200)
    assert res_emergencia["nivel"] == 3


def test_nom035_pdf_generation():
    ruta_pdf = generar_reporte_nom035("6ab71217a7a8febb21ccf29f")
    assert ruta_pdf is not None
    assert os.path.isfile(ruta_pdf)
    assert os.path.getsize(ruta_pdf) > 1000
    with open(ruta_pdf, "rb") as f:
        assert f.read(4) == b"%PDF"


def test_docker_infrastructure_files_exist():
    assert os.path.isfile(os.path.join(ROOT_DIR, "Dockerfile"))
    assert os.path.isfile(os.path.join(ROOT_DIR, "docker-compose.yml"))
    assert os.path.isfile(os.path.join(ROOT_DIR, "mosquitto", "config", "mosquitto.conf"))
