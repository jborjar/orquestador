"""
Evolution API - Funciones para WhatsApp
"""
import base64

import requests
from fastapi import HTTPException

from config import EVOLUTION_URL, EVOLUTION_API_KEY
from utils import detect_audio_format, detect_image_format, detect_doc_format


def get_evolution_headers() -> dict:
    """Headers para Evolution API."""
    headers = {"Content-Type": "application/json"}
    if EVOLUTION_API_KEY:
        headers["apikey"] = EVOLUTION_API_KEY
    return headers


def get_media_from_evolution(instance: str, data: dict) -> str:
    """
    Obtiene el media decodificado desde Evolution API.
    Usa el endpoint /chat/getBase64FromMediaMessage que desencripta el media.
    """
    url = f"{EVOLUTION_URL}/chat/getBase64FromMediaMessage/{instance}"
    key = data.get("key", {})
    message = data.get("message", {})

    payload = {
        "message": {"key": key, "message": message},
        "convertToMp4": False
    }

    print(f"[DEBUG] Obteniendo media de Evolution: {url}")
    try:
        r = requests.post(url, json=payload, headers=get_evolution_headers(), timeout=60)
        r.raise_for_status()
        result = r.json()
        media_b64 = result.get("base64", "")
        if not media_b64:
            raise HTTPException(status_code=502, detail="Evolution no retorno base64")
        print(f"[DEBUG] Media obtenido de Evolution: {len(media_b64)} chars")
        return media_b64
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Error obteniendo media de Evolution: {e}")


def get_media_bytes(data: dict, msg_key: str, media_type: str, instance: str) -> tuple:
    """
    Obtiene los bytes del media desde Evolution API.
    El media de WhatsApp viene encriptado, Evolution lo desencripta.

    Returns:
        tuple: (media_bytes, mimetype, extension)
    """
    message = data.get("message", {})
    msg_data = message.get(msg_key, {})
    filename = msg_data.get("fileName", "")
    mimetype = msg_data.get("mimetype", "")

    media_b64 = get_media_from_evolution(instance, data)

    if "," in media_b64:
        media_b64 = media_b64.split(",", 1)[1]

    media_bytes = base64.b64decode(media_b64)

    if media_type == "audio":
        extension = detect_audio_format(media_bytes)
    elif media_type == "image":
        extension = detect_image_format(media_bytes)
    elif media_type == "document":
        extension = detect_doc_format(media_bytes, filename)
    else:
        extension = ".bin"

    print(f"[DEBUG] Media {media_type}: {len(media_bytes)} bytes, mimetype={mimetype}, formato={extension}")
    return media_bytes, mimetype, extension


def extract_number(remote_jid: str) -> str:
    """Extrae el numero del remoteJid."""
    if "@" in remote_jid:
        return remote_jid.split("@")[0]
    return remote_jid


def send_text_message(instance: str, remote_jid: str, text: str):
    """Envia mensaje de texto via Evolution."""
    url = f"{EVOLUTION_URL}/message/sendText/{instance}"
    number = extract_number(remote_jid)
    payload = {"number": number, "text": text}
    print(f"[DEBUG] Enviando texto a {number}: {text[:50]}...")
    try:
        r = requests.post(url, json=payload, headers=get_evolution_headers(), timeout=30)
        r.raise_for_status()
        print(f"[DEBUG] Texto enviado OK")
    except Exception as e:
        print(f"Error enviando texto a {number}: {e}")


def send_audio_message(instance: str, remote_jid: str, audio_b64: str):
    """Envia nota de voz via Evolution."""
    url = f"{EVOLUTION_URL}/message/sendWhatsAppAudio/{instance}"
    number = extract_number(remote_jid)
    payload = {"number": number, "audio": audio_b64}
    print(f"[DEBUG] Enviando audio a {number} ({len(audio_b64)} chars)")
    try:
        r = requests.post(url, json=payload, headers=get_evolution_headers(), timeout=60)
        if r.status_code not in (200, 201):
            print(f"[DEBUG] Error Evolution audio: {r.status_code} - {r.text[:500]}")
        r.raise_for_status()
        print(f"[DEBUG] Audio enviado OK")
    except Exception as e:
        print(f"Error enviando audio a {number}: {e}")


def send_presence(instance: str, remote_jid: str, presence: str = "composing"):
    """
    Envia estado de presencia via Evolution.

    presence puede ser:
    - "composing" (escribiendo...)
    - "recording" (grabando audio...)
    - "paused" (detener indicador)
    """
    url = f"{EVOLUTION_URL}/chat/sendPresence/{instance}"
    number = extract_number(remote_jid)
    payload = {"number": number, "presence": presence, "delay": 1200}
    try:
        r = requests.post(url, json=payload, headers=get_evolution_headers(), timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"Error enviando presencia: {e}")
