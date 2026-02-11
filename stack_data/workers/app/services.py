"""
Servicios de IA - Llamadas a la API unificada y servicios individuales
"""
import json
import os
from typing import List, Optional

import requests
from fastapi import HTTPException

from config import API_URL, LLM_URL, STT_URL, TTS_URL, NOMBRE_IA

# Cargar prompts al iniciar
PROMPTS_FILE = os.path.join(os.path.dirname(__file__), "prompts.json")
_prompts_cache = None


def get_prompts() -> dict:
    """Carga los prompts desde el archivo JSON (con cache)."""
    global _prompts_cache
    if _prompts_cache is None:
        try:
            with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
                _prompts_cache = json.load(f)
        except Exception as e:
            print(f"Error cargando prompts.json: {e}")
            _prompts_cache = {}
    return _prompts_cache


def get_system_prompt(prompt_key: str = "default") -> str:
    """Obtiene un system prompt por su clave, inyectando el nombre del asistente."""
    prompts = get_prompts()
    if prompt_key in prompts:
        base_prompt = prompts[prompt_key].get("prompt", "")
    else:
        base_prompt = prompts.get("default", {}).get("prompt", "Eres un asistente útil.")

    # Instrucciones generales de comportamiento (aplican a todos los intents)
    behavior_instruction = "Responde de forma breve, explícita y formal. Evita rodeos y ve directo al punto."

    # Instrucción sobre capacidades de audio/voz
    audio_instruction = (
        "IMPORTANTE: Si el usuario menciona audio, voz, o te pide que hables, "
        "simplemente responde con texto normal. El sistema automáticamente "
        "convertirá tu respuesta a audio. NUNCA digas que no puedes generar audio o voz."
    )

    return f"Tu nombre es {NOMBRE_IA}. {base_prompt} {behavior_instruction} {audio_instruction}"


def reload_prompts():
    """Recarga los prompts desde el archivo (para cambios en caliente)."""
    global _prompts_cache
    _prompts_cache = None
    return get_prompts()


# =============================================================
#   API UNIFICADA (agente_ia:8000)
# =============================================================

def api_chat(message: str, system_prompt: Optional[str] = None, history: Optional[List[dict]] = None) -> dict:
    """
    Llama a la API unificada /chat.
    Retorna: {texto, audio_b64, idioma}
    """
    payload = {"texto": message}
    if system_prompt:
        payload["system_prompt"] = system_prompt
    if history:
        payload["historial"] = history

    try:
        r = requests.post(f"{API_URL}/chat", json=payload, timeout=600)
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Error al conectar con API: {e}")

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"API respondio {r.status_code}: {r.text}")

    return r.json()


def api_voice(audio_b64: str, system_prompt: Optional[str] = None, history: Optional[List[dict]] = None) -> dict:
    """
    Llama a la API unificada /voice.
    Retorna: {texto, audio_b64, idioma, transcripcion}
    """
    payload = {"audio_b64": audio_b64}
    if system_prompt:
        payload["system_prompt"] = system_prompt
    if history:
        payload["historial"] = history

    try:
        r = requests.post(f"{API_URL}/voice", json=payload, timeout=600)
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Error al conectar con API: {e}")

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"API respondio {r.status_code}: {r.text}")

    return r.json()


def api_image(image_b64: str, prompt: Optional[str] = None) -> dict:
    """
    Llama a la API unificada /image.
    Retorna: {texto, audio_b64, idioma}
    """
    payload = {"imagen_b64": image_b64}
    if prompt:
        payload["prompt"] = prompt

    try:
        r = requests.post(f"{API_URL}/image", json=payload, timeout=600)
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Error al conectar con API: {e}")

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"API respondio {r.status_code}: {r.text}")

    return r.json()


def api_document(document_b64: str, filename: str, prompt: Optional[str] = None) -> dict:
    """
    Llama a la API unificada /document.
    Retorna: {texto, audio_b64, idioma, paginas}
    """
    payload = {
        "documento_b64": document_b64,
        "filename": filename
    }
    if prompt:
        payload["prompt"] = prompt

    try:
        r = requests.post(f"{API_URL}/document", json=payload, timeout=600)
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Error al conectar con API: {e}")

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"API respondio {r.status_code}: {r.text}")

    return r.json()


def api_classify(document_b64: str, filename: str, categories: List[str]) -> dict:
    """
    Llama a la API unificada /classify.
    Retorna: {categoria, confianza, razon, audio_b64}
    """
    payload = {
        "documento_b64": document_b64,
        "filename": filename,
        "categorias": categories
    }

    try:
        r = requests.post(f"{API_URL}/classify", json=payload, timeout=600)
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Error al conectar con API: {e}")

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"API respondio {r.status_code}: {r.text}")

    return r.json()


# =============================================================
#   SERVICIOS INDIVIDUALES (llamadas directas)
# =============================================================

def call_ollama_chat(model: str, messages: List[dict], stream: bool = False) -> str:
    """Llama a Ollama /api/chat y regresa el texto de la respuesta."""
    url = f"{LLM_URL}/api/chat"
    payload = {"model": model, "messages": messages, "stream": stream}

    try:
        r = requests.post(url, json=payload, timeout=600)
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Error al conectar con Ollama: {e}")

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Ollama respondio {r.status_code}: {r.text}")

    data = r.json()
    try:
        return data["message"]["content"]
    except Exception:
        if "content" in data:
            return data["content"]
        raise HTTPException(status_code=500, detail="No se pudo extraer respuesta de Ollama.")


def call_llm_chat(model: str, messages: List[dict], channel: str, user_id: str) -> dict:
    """
    Llama al endpoint /llm_chat de agente_ia.
    Retorna: {"content": str, "language": str}
    """
    url = f"{API_URL}/llm_chat"
    payload = {
        "model": model,
        "messages": messages,
        "channel": channel,
        "user_id": user_id
    }

    try:
        r = requests.post(url, json=payload, timeout=600)
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Error al conectar con API: {e}")

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"API respondio {r.status_code}: {r.text}")

    data = r.json()
    return {
        "content": data.get("message", {}).get("content", ""),
        "language": data.get("message", {}).get("language", "es")
    }


def call_stt(audio_bytes: bytes, filename: str) -> dict:
    """Llama al servicio STT para transcribir audio."""
    try:
        files = {"audio": (filename, audio_bytes)}
        r = requests.post(f"{STT_URL}/transcribe", files=files, timeout=120)
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Error al conectar con STT: {e}")

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"STT respondio {r.status_code}: {r.text}")

    return r.json()


def call_tts(texto: str, idioma: Optional[str] = None) -> bytes:
    """Llama al servicio TTS para sintetizar audio."""
    try:
        payload = {"texto": texto}
        if idioma:
            payload["idioma"] = idioma
        r = requests.post(f"{TTS_URL}/synthesize", json=payload, timeout=120)
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Error al conectar con TTS: {e}")

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"TTS respondio {r.status_code}: {r.text}")

    return r.content
