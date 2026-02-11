#!/usr/bin/env python3
# =============================================================
# Autoscaler - Escalado automatico de workers
# =============================================================
# Monitorea la cola de Redis y ajusta el numero de workers
# segun la cantidad de mensajes pendientes.
#
# Umbrales:
#   - cola > SCALE_UP_THRESHOLD (20): escalar arriba
#   - cola < SCALE_DOWN_THRESHOLD (10): escalar abajo
# =============================================================

import os
import time
import logging
import redis
import docker

# Configuracion de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configuracion desde variables de entorno
REDIS_URL = os.getenv("REDIS_URL", "redis://:orquestador123@redis-orquestador:6379/0")
QUEUE_KEY = os.getenv("QUEUE_KEY", "mensajes:pendientes")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30"))  # segundos

# Umbrales de escalado
SCALE_UP_THRESHOLD = int(os.getenv("SCALE_UP_THRESHOLD", "20"))
SCALE_DOWN_THRESHOLD = int(os.getenv("SCALE_DOWN_THRESHOLD", "10"))
MIN_WORKERS = int(os.getenv("MIN_WORKERS", "1"))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "5"))

# Configuracion Docker
COMPOSE_PROJECT = os.getenv("COMPOSE_PROJECT", "orquestador")
WORKER_SERVICE = os.getenv("WORKER_SERVICE", "workers")

# Cooldown entre escalados (evitar flapping)
SCALE_COOLDOWN = int(os.getenv("SCALE_COOLDOWN", "60"))  # segundos
last_scale_time = 0


def get_redis_connection():
    """Conectar a Redis."""
    return redis.from_url(REDIS_URL, decode_responses=True)


def get_queue_length(r: redis.Redis) -> int:
    """Obtener longitud de la cola de mensajes."""
    try:
        # Intentar obtener longitud de lista
        length = r.llen(QUEUE_KEY)
        return length
    except Exception as e:
        logger.error(f"Error obteniendo longitud de cola: {e}")
        return 0


def get_current_workers(client: docker.DockerClient) -> int:
    """Contar workers actualmente corriendo."""
    try:
        containers = client.containers.list(
            filters={
                "label": f"com.docker.compose.project={COMPOSE_PROJECT}",
                "name": WORKER_SERVICE
            }
        )
        return len(containers)
    except Exception as e:
        logger.error(f"Error contando workers: {e}")
        return 1


def scale_workers(client: docker.DockerClient, target: int) -> bool:
    """Escalar workers al numero objetivo."""
    global last_scale_time

    # Verificar cooldown
    now = time.time()
    if now - last_scale_time < SCALE_COOLDOWN:
        logger.debug(f"Cooldown activo, esperando {SCALE_COOLDOWN - (now - last_scale_time):.0f}s")
        return False

    # Limitar a rango permitido
    target = max(MIN_WORKERS, min(MAX_WORKERS, target))

    try:
        # Usar docker compose scale via CLI
        # Esto es mas confiable que la API de Docker para compose
        import subprocess

        result = subprocess.run(
            ["docker", "compose", "-p", COMPOSE_PROJECT, "up", "-d", "--scale", f"{WORKER_SERVICE}={target}", "--no-recreate"],
            capture_output=True,
            text=True,
            cwd="/opt/stacks/orquestador"
        )

        if result.returncode == 0:
            logger.info(f"Workers escalados a {target}")
            last_scale_time = now
            return True
        else:
            logger.error(f"Error escalando: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"Error escalando workers: {e}")
        return False


def main():
    """Loop principal del autoscaler."""
    logger.info("=" * 50)
    logger.info("Autoscaler iniciado")
    logger.info("=" * 50)
    logger.info(f"Configuracion:")
    logger.info(f"  - Cola Redis: {QUEUE_KEY}")
    logger.info(f"  - Umbral escalar arriba: > {SCALE_UP_THRESHOLD}")
    logger.info(f"  - Umbral escalar abajo: < {SCALE_DOWN_THRESHOLD}")
    logger.info(f"  - Workers minimos: {MIN_WORKERS}")
    logger.info(f"  - Workers maximos: {MAX_WORKERS}")
    logger.info(f"  - Intervalo de chequeo: {CHECK_INTERVAL}s")
    logger.info(f"  - Cooldown entre escalados: {SCALE_COOLDOWN}s")
    logger.info("=" * 50)

    # Conectar a Redis y Docker
    r = get_redis_connection()
    docker_client = docker.from_env()

    # Verificar conexion
    try:
        r.ping()
        logger.info("Conexion a Redis OK")
    except Exception as e:
        logger.error(f"Error conectando a Redis: {e}")
        return

    try:
        docker_client.ping()
        logger.info("Conexion a Docker OK")
    except Exception as e:
        logger.error(f"Error conectando a Docker: {e}")
        return

    # Loop principal
    while True:
        try:
            queue_length = get_queue_length(r)
            current_workers = get_current_workers(docker_client)

            logger.info(f"Cola: {queue_length} | Workers: {current_workers}")

            # Decidir si escalar
            if queue_length > SCALE_UP_THRESHOLD and current_workers < MAX_WORKERS:
                new_count = min(current_workers + 1, MAX_WORKERS)
                logger.info(f"Cola > {SCALE_UP_THRESHOLD}, escalando de {current_workers} a {new_count}")
                scale_workers(docker_client, new_count)

            elif queue_length < SCALE_DOWN_THRESHOLD and current_workers > MIN_WORKERS:
                new_count = max(current_workers - 1, MIN_WORKERS)
                logger.info(f"Cola < {SCALE_DOWN_THRESHOLD}, reduciendo de {current_workers} a {new_count}")
                scale_workers(docker_client, new_count)

        except Exception as e:
            logger.error(f"Error en loop principal: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
