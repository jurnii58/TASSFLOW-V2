import os
import math

NIVELES_METADATA = {
    0: {
        "etiqueta": "Normal / Fisico",
        "descripcion": "Actividad fisiologica normal o elevacion explicada por movimiento motriz.",
        "accion": "NINGUNA",
        "color": "#30d158" # Verde
    },
    1: {
        "etiqueta": "Atencion (Fatiga)",
        "descripcion": "Ligero incremento de ritmo cardiaco en reposo. Fatiga mental acumulada.",
        "accion": "MONITOREO_ACTIVO",
        "color": "#ffd60a" # Amarillo
    },
    2: {
        "etiqueta": "Estres Agudo Sedentario",
        "descripcion": "Sobrecarga cognitiva severa: Taquicardia sin movimiento fisico registrado.",
        "accion": "PAUSA_FORZADA_478",
        "color": "#ff9f0a" # Naranja
    },
    3: {
        "etiqueta": "Emergencia Medica Critica",
        "descripcion": "Frecuencia cardiaca anomala extrema (>150 BPM) sostenida en reposo absoluto.",
        "accion": "ALERTA_BRIGADISTA_MEDICO",
        "color": "#ff453a" # Rojo
    }
}

class DecisionTreeContext:
    """Arbol de decision individual para el ensamble Random Forest"""
    def __init__(self, seed=42):
        self.seed = seed

    def evaluate(self, delta_bpm, bpm, acc_dinamica, tiempo_sedentario_s):
        # 1. Regla crítica médica (prioridad absoluta)
        if bpm >= 150.0 and acc_dinamica < 0.25:
            return 3

        # 2. Esfuerzo físico motriz evidente: aceleración dinámica > 0.40 g
        if acc_dinamica >= 0.40:
            return 0

        # 3. Transición de movimiento moderado
        if acc_dinamica >= 0.25 and bpm < 135.0:
            return 0

        # 4. Sobrecarga aguda en reposo sedentario (Nivel 2)
        if (delta_bpm >= 35.0 or bpm >= 120.0) and acc_dinamica < 0.20:
            return 2

        # 5. Fatiga moderada / Atención (Nivel 1)
        if (delta_bpm >= 18.0 or bpm >= 92.0) and acc_dinamica < 0.22:
            return 1

        # 6. Estado basal normal
        return 0

class RandomForestContextClassifier:
    """
    Ensamble de Árboles de Decisión (Random Forest Context Classifier)
    construido en Python puro para máxima portabilidad y resiliencia.
    """
    def __init__(self, n_trees=5):
        self.trees = [DecisionTreeContext(seed=i) for i in range(n_trees)]

    def predecir(self, delta_bpm, bpm, acc_magnitude, tiempo_sedentario_s):
        # Aceleración dinámica: filtra el vector estático de gravedad terrestre (|a| - 1g)
        acc_dinamica = abs(acc_magnitude - 1.0) if acc_magnitude > 0.5 else acc_magnitude

        # Votación por ensamble
        votos = {0: 0, 1: 0, 2: 0, 3: 0}
        for tree in self.trees:
            pred = tree.evaluate(delta_bpm, bpm, acc_dinamica, tiempo_sedentario_s)
            votos[pred] += 1

        # Regla de seguridad médica
        if bpm >= 150.0 and acc_dinamica < 0.25:
            nivel_final = 3
        else:
            nivel_final = max(votos, key=votos.get)

        info = NIVELES_METADATA.get(nivel_final, NIVELES_METADATA[0])
        return {
            "nivel": nivel_final,
            "etiqueta": info["etiqueta"],
            "descripcion": info["descripcion"],
            "accion": info["accion"],
            "color": info["color"],
            "bpm": round(bpm, 1),
            "delta_bpm": round(delta_bpm, 1),
            "acc_magnitude": round(acc_magnitude, 3),
            "acc_dinamica": round(acc_dinamica, 3),
            "tiempo_sedentario_s": int(tiempo_sedentario_s)
        }

clasificador_biometrico = RandomForestContextClassifier()
