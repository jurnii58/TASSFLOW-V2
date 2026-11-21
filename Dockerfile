# ==============================================================================
# TASSFLOW v2.0 - Dockerfile Oficial (Flask + SocketIO + ML Random Forest + Spark Edge)
# ==============================================================================
FROM python:3.12-slim

LABEL maintainer="Equipo TASSFLOW v2.0 - Salud Ocupacional NOM-035"
LABEL description="Motor de Telemetría Biométrica a 1 Hz, Clasificador Random Forest y Radar WebSockets"

# Evitar archivos .pyc y habilitar logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000

WORKDIR /app

# Instalar dependencias del sistema ligeras
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el código de la aplicación
COPY . .

# Exponer puerto HTTP / WebSockets
EXPOSE 5000

# Verificación de salud del contenedor
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/login || exit 1

# Comando de arranque del servidor unificado Flask + SocketIO
CMD ["python", "run.py"]
