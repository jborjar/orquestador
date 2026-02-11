"""
Cliente Redis - Historial de conversaciones
"""
import json
import redis

from config import REDIS_URL, MAX_HISTORY, HISTORY_TTL

_redis_client = None


def get_redis() -> redis.Redis:
    """Obtiene conexion a Redis (lazy init)."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def get_conversation_history(channel: str, user_id: str) -> list:
    """Obtiene historial de conversacion desde Redis."""
    try:
        r = get_redis()
        key = f"chat:history:{channel}:{user_id}"
        data = r.get(key)
        if data:
            return json.loads(data)
        return []
    except Exception as e:
        print(f"Error obteniendo historial de Redis: {e}")
        return []


def add_to_history(channel: str, user_id: str, role: str, content: str):
    """Agrega mensaje al historial en Redis."""
    try:
        r = get_redis()
        key = f"chat:history:{channel}:{user_id}"
        history = get_conversation_history(channel, user_id)
        history.append({"role": role, "content": content})
        if len(history) > MAX_HISTORY:
            history = history[-MAX_HISTORY:]
        r.setex(key, HISTORY_TTL, json.dumps(history))
    except Exception as e:
        print(f"Error guardando historial en Redis: {e}")


def get_user_intent(channel: str, user_id: str) -> str:
    """Obtiene el intent actual del usuario desde Redis."""
    try:
        r = get_redis()
        key = f"chat:intent:{channel}:{user_id}"
        intent = r.get(key)
        return intent if intent else "default"
    except Exception as e:
        print(f"Error obteniendo intent de Redis: {e}")
        return "default"


def set_user_intent(channel: str, user_id: str, intent: str):
    """Guarda el intent actual del usuario en Redis."""
    try:
        r = get_redis()
        key = f"chat:intent:{channel}:{user_id}"
        r.setex(key, HISTORY_TTL, intent)
    except Exception as e:
        print(f"Error guardando intent en Redis: {e}")


def get_user_language(channel: str, user_id: str) -> str:
    """Obtiene el idioma del usuario desde Redis."""
    try:
        r = get_redis()
        key = f"chat:language:{channel}:{user_id}"
        language = r.get(key)
        return language if language else "es"
    except Exception as e:
        print(f"Error obteniendo idioma de Redis: {e}")
        return "es"


def set_user_language(channel: str, user_id: str, language: str):
    """Guarda el idioma del usuario en Redis."""
    try:
        r = get_redis()
        key = f"chat:language:{channel}:{user_id}"
        r.setex(key, HISTORY_TTL, language)
    except Exception as e:
        print(f"Error guardando idioma en Redis: {e}")
