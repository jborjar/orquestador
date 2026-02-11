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


# TTL corto para contexto de documentos (10 minutos)
DOCUMENT_TTL = 600
# Maximo de documentos en contexto
MAX_DOCUMENTS = 3
# Maximo de caracteres por documento
MAX_DOC_CHARS = 5000


def get_user_documents(channel: str, user_id: str) -> list:
    """Obtiene la lista de documentos del usuario desde Redis."""
    try:
        r = get_redis()
        key = f"chat:documents:{channel}:{user_id}"
        data = r.get(key)
        if data:
            return json.loads(data)
        return []
    except Exception as e:
        print(f"Error obteniendo documentos de Redis: {e}")
        return []


def add_user_document(channel: str, user_id: str, filename: str, text: str):
    """Agrega un documento al contexto del usuario (maximo 3 docs)."""
    try:
        r = get_redis()
        key = f"chat:documents:{channel}:{user_id}"

        # Obtener documentos existentes
        documents = get_user_documents(channel, user_id)

        # Agregar nuevo documento
        new_doc = {
            "filename": filename,
            "text": text[:MAX_DOC_CHARS]
        }
        documents.append(new_doc)

        # Mantener solo los ultimos N documentos
        if len(documents) > MAX_DOCUMENTS:
            documents = documents[-MAX_DOCUMENTS:]

        r.setex(key, DOCUMENT_TTL, json.dumps(documents))
        print(f"[DEBUG] Documento agregado: {filename} ({len(documents)} docs en contexto)")
    except Exception as e:
        print(f"Error guardando documento en Redis: {e}")


def clear_user_documents(channel: str, user_id: str):
    """Elimina todos los documentos del usuario."""
    try:
        r = get_redis()
        key = f"chat:documents:{channel}:{user_id}"
        r.delete(key)
        print(f"[DEBUG] Documentos eliminados del contexto")
    except Exception as e:
        print(f"Error eliminando documentos de Redis: {e}")


# Compatibilidad con codigo anterior (deprecado)
def get_user_document(channel: str, user_id: str) -> dict:
    """DEPRECADO: Usa get_user_documents(). Retorna el ultimo documento."""
    docs = get_user_documents(channel, user_id)
    return docs[-1] if docs else {}


def set_user_document(channel: str, user_id: str, filename: str, text: str):
    """DEPRECADO: Usa add_user_document()."""
    add_user_document(channel, user_id, filename, text)


def clear_user_document(channel: str, user_id: str):
    """DEPRECADO: Usa clear_user_documents()."""
    clear_user_documents(channel, user_id)


# TTL para deduplicacion de mensajes (5 minutos)
DEDUP_TTL = 300


def is_message_processed(message_id: str) -> bool:
    """
    Verifica si un mensaje ya fue procesado (deduplicacion).
    Usa SETNX para atomicamente verificar y marcar.
    Retorna True si YA fue procesado (ignorar), False si es nuevo.
    """
    if not message_id:
        return False  # Sin ID, procesar siempre

    try:
        r = get_redis()
        key = f"webhook:processed:{message_id}"
        # SETNX retorna True si se creo la key (mensaje nuevo)
        # Retorna False si la key ya existia (mensaje duplicado)
        was_set = r.setnx(key, "1")
        if was_set:
            # Mensaje nuevo, establecer TTL
            r.expire(key, DEDUP_TTL)
            return False  # No fue procesado antes
        return True  # Ya fue procesado
    except Exception as e:
        print(f"Error en deduplicacion: {e}")
        return False  # En caso de error, procesar
