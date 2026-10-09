import collections
from datetime import datetime, timedelta

# Verificación de disponibilidad de PySpark y Java
PYSPARK_DISPONIBLE = False
try:
    from pyspark.sql import SparkSession
    from pyspark.sql.functions import from_json, col, window, avg, max as spark_max, when
    from pyspark.sql.types import StructType, StructField, StringType, DoubleType, TimestampType
    PYSPARK_DISPONIBLE = True
except ImportError:
    pass

class EdgeSlidingWindowEngine:
    """
    Motor Edge de Ventana Deslizante (5 segundos, 10s watermark).
    Emula la arquitectura de Apache Spark Structured Streaming en modo ultraligero
    para entornos Edge (Tauri / Electron / Servidor sin JVM).
    """
    def __init__(self, tamano_ventana_seg=5, watermark_seg=10):
        self.tamano_ventana = tamano_ventana_seg
        self.watermark = watermark_seg
        self.buffer = collections.defaultdict(list) # usuario_id -> [(timestamp, bpm, acc_mag)]

    def agregar_lectura(self, usuario_id, bpm, acc_magnitude, timestamp=None):
        ts = timestamp or datetime.now()
        self.buffer[usuario_id].append((ts, bpm, acc_magnitude))
        
        # Filtrar datos anteriores al watermark de 10s
        limite_watermark = ts - timedelta(seconds=self.watermark)
        self.buffer[usuario_id] = [item for item in self.buffer[usuario_id] if item[0] >= limite_watermark]

        # Calcular agregaciones de la ventana deslizante (últimos 5 segundos)
        limite_ventana = ts - timedelta(seconds=self.tamano_ventana)
        ventana_actual = [item for item in self.buffer[usuario_id] if item[0] >= limite_ventana]
        
        if not ventana_actual:
            return None

        bpm_valores = [item[1] for item in ventana_actual]
        acc_valores = [item[2] for item in ventana_actual]

        bpm_filtrado = sum(bpm_valores) / len(bpm_valores)
        acc_filtrado = sum(acc_valores) / len(acc_valores)
        bpm_pico = max(bpm_valores)

        # Reglas de anomalía biológica equivalentes a Spark Structured Streaming
        if bpm_filtrado >= 150.0 and acc_filtrado < 0.25:
            alerta = "EMERGENCIA_MEDICA"
        elif bpm_filtrado >= 120.0 and acc_filtrado < 0.20:
            alerta = "ESTRES_AGUDO"
        else:
            alerta = "NORMAL"

        return {
            "usuario_id": usuario_id,
            "ventana_seg": self.tamano_ventana,
            "muestras_en_ventana": len(ventana_actual),
            "bpm_filtrado": round(bpm_filtrado, 1),
            "acc_filtrado": round(acc_filtrado, 3),
            "bpm_pico": round(bpm_pico, 1),
            "alerta_estres": alerta,
            "timestamp": ts.isoformat()
        }

def crear_spark_streaming_session():
    """Inicializa la sesión de Apache Spark Structured Streaming si JVM está instalada"""
    if not PYSPARK_DISPONIBLE:
        raise RuntimeError("PySpark no esta instalado en este entorno de Python.")
    
    os.environ['PYSPARK_PYTHON'] = sys.executable
    os.environ['PYSPARK_DRIVER_PYTHON'] = sys.executable

    spark = SparkSession.builder \
        .appName("TASSFLOW_Biometric_Structured_Streaming") \
        .master("local[*]") \
        .config("spark.sql.shuffle.partitions", "2") \
        .config("spark.default.parallelism", "2") \
        .getOrCreate()
        
    spark.sparkContext.setLogLevel("WARN")
    return spark

def construir_pipeline_streaming(spark, host="localhost", port=9999):
    """
    Pipeline de Streaming continuo de Spark:
    1. Ingesta de telemetría por socket o broker.
    2. Ventanas de tiempo rodantes de 5 segundos para filtrado de ruido biológico.
    3. Detección de anomalías biológicas en tiempo real.
    """
    schema = StructType([
        StructField("usuario_id", StringType(), True),
        StructField("empresa_id", StringType(), True),
        StructField("bpm", DoubleType(), True),
        StructField("acc_magnitude", DoubleType(), True),
        StructField("timestamp", TimestampType(), True)
    ])
    
    raw_stream = spark.readStream \
        .format("socket") \
        .option("host", host) \
        .option("port", port) \
        .load()
        
    parsed_stream = raw_stream.select(from_json(col("value"), schema).alias("data")).select("data.*")
    
    windowed_stream = parsed_stream \
        .withWatermark("timestamp", "10 seconds") \
        .groupBy(
            window(col("timestamp"), "5 seconds", "1 second"),
            col("usuario_id"),
            col("empresa_id")
        ) \
        .agg(
            avg("bpm").alias("bpm_filtrado"),
            avg("acc_magnitude").alias("acc_filtrado"),
            spark_max("bpm").alias("bpm_pico")
        ) \
        .withColumn(
            "alerta_estres",
            when((col("bpm_filtrado") >= 120.0) & (col("acc_filtrado") < 0.20), "ESTRES_AGUDO")
            .when((col("bpm_filtrado") >= 150.0) & (col("acc_filtrado") < 0.25), "EMERGENCIA_MEDICA")
            .otherwise("NORMAL")
        )
        
    return windowed_stream

if __name__ == "__main__":
    print("[TASSFLOW v2.0] Verificando Motor de Streaming de Telemetria...")
    if PYSPARK_DISPONIBLE:
        try:
            spark = crear_spark_streaming_session()
            print("[OK] Motor Apache Spark inicializado correctamente.")
            stream = construir_pipeline_streaming(spark)
            query = stream.writeStream \
                .outputMode("update") \
                .format("console") \
                .option("truncate", "false") \
                .start()
            print("[STREAM] Escuchando ventana de 5 segundos en tiempo real...")
            query.awaitTermination()
        except Exception as e:
            print(f"[INFO] Modo Spark finalizado o en espera de JVM: {e}")
    else:
        print("[INFO] PySpark o Java no detectados. Ejecutando Motor Edge Sliding Window (5s / 10s watermark)...")
        engine = EdgeSlidingWindowEngine(tamano_ventana_seg=5, watermark_seg=10)
        # Test con 5 lecturas consecutivas
        now = datetime.now()
        for i in range(5):
            res = engine.agregar_lectura("usr_01", 125.0 + i, 0.05, now + timedelta(seconds=i))
        print(f"[OK] Ventana calculada exitosamente: {res}")
