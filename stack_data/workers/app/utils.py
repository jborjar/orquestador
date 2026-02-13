"""
Utilidades - Deteccion de formatos
"""
import os

# Magic bytes para deteccion de formato
AUDIO_SIGNATURES = {
    b'OggS': '.ogg',
    b'fLaC': '.flac',
    b'RIFF': '.wav',
    b'\xff\xfb': '.mp3',
    b'\xff\xfa': '.mp3',
    b'\xff\xf3': '.mp3',
    b'\xff\xf2': '.mp3',
    b'ID3': '.mp3',
}

IMAGE_SIGNATURES = {
    b'\xff\xd8\xff': '.jpg',
    b'\x89PNG\r\n\x1a\n': '.png',
    b'GIF87a': '.gif',
    b'GIF89a': '.gif',
    b'RIFF': '.webp',
    b'BM': '.bmp',
}

DOC_SIGNATURES = {
    b'%PDF': '.pdf',
    b'PK\x03\x04': '.docx',
    b'\xd0\xcf\x11\xe0': '.doc',
}


def detect_audio_format(data: bytes) -> str:
    """Detecta formato de audio desde magic bytes."""
    for signature, ext in AUDIO_SIGNATURES.items():
        if data.startswith(signature):
            return ext
    if len(data) > 8 and data[4:8] == b'ftyp':
        return '.m4a'
    return '.ogg'


def detect_image_format(data: bytes) -> str:
    """Detecta formato de imagen desde magic bytes."""
    for signature, ext in IMAGE_SIGNATURES.items():
        if data.startswith(signature):
            if signature == b'RIFF' and len(data) > 12:
                if data[8:12] == b'WEBP':
                    return '.webp'
                continue
            return ext
    return '.jpg'


def detect_doc_format(data: bytes, filename: str = "") -> str:
    """Detecta formato de documento desde magic bytes o nombre de archivo."""
    for signature, ext in DOC_SIGNATURES.items():
        if data.startswith(signature):
            if ext == '.docx' and filename:
                lower_name = filename.lower()
                if lower_name.endswith('.xlsx'):
                    return '.xlsx'
                elif lower_name.endswith('.pptx'):
                    return '.pptx'
            return ext
    if filename:
        ext = os.path.splitext(filename.lower())[1]
        if ext:
            return ext
    return '.pdf'


def detect_wants_audio(text: str) -> bool:
    """
    Detecta si el usuario quiere respuesta en audio basado en el texto.
    Busca palabras clave que indiquen preferencia por audio.
    """
    if not text:
        return False
    text_lower = text.lower()
    audio_keywords = [
        "audio", "voz", "escuchar", "dime", "cuéntame", "cuentame",
        "háblame", "hablame", "lee", "leer", "reproduce",
        "hablar", "habla", "puedes hablar", "sabes hablar"
    ]
    return any(keyword in text_lower for keyword in audio_keywords)


def detect_wants_text(text: str) -> bool:
    """
    Detecta si el usuario quiere respuesta en texto basado en el texto.
    Busca palabras clave que indiquen preferencia por texto.
    """
    if not text:
        return False
    text_lower = text.lower()
    text_keywords = [
        "texto", "escribe", "escríbeme", "escribeme", "manda texto",
        "responde texto", "en texto", "por texto", "mensaje de texto",
        "no audio", "sin audio", "sin voz"
    ]
    return any(keyword in text_lower for keyword in text_keywords)


# Mensajes de disculpa por audio solo en español (en diferentes idiomas)
SPANISH_ONLY_MESSAGES = {
    "en": "[Audio only available in Spanish. Here is the text response:]",
    "de": "[Audio nur auf Spanisch verfügbar. Hier ist die Textantwort:]",
    "fr": "[Audio disponible uniquement en espagnol. Voici la réponse texte:]",
    "pt": "[Áudio disponível apenas em espanhol. Aqui está a resposta em texto:]",
    "it": "[Audio disponibile solo in spagnolo. Ecco la risposta testuale:]",
    "zh": "[音频仅提供西班牙语。以下是文字回复：]",
    "ja": "[音声はスペイン語のみです。テキスト回答はこちら：]",
    "ko": "[오디오는 스페인어로만 제공됩니다. 텍스트 응답:]",
    "ru": "[Аудио доступно только на испанском. Текстовый ответ:]",
    "ar": "[الصوت متاح بالإسبانية فقط. إليك الرد النصي:]",
    "tr": "[Ses yalnızca İspanyolca olarak mevcuttur. İşte metin yanıtı:]",
    "nl": "[Audio alleen beschikbaar in het Spaans. Hier is het tekstantwoord:]",
    "pl": "[Dźwięk dostępny tylko po hiszpańsku. Oto odpowiedź tekstowa:]",
    "uk": "[Аудіо доступне лише іспанською. Ось текстова відповідь:]",
    "hi": "[ऑडियो केवल स्पेनिश में उपलब्ध है। यहां टेक्स्ट प्रतिक्रिया है:]",
    "default": "[Audio only available in Spanish. Here is the text response:]"
}


def detect_response_language(text: str) -> str:
    """
    Detecta el idioma del texto usando langdetect.
    Retorna código de 2 letras (es, en, de, etc.) o 'es' por defecto.
    """
    if not text or len(text.strip()) < 10:
        return "es"
    try:
        from langdetect import detect
        return detect(text)
    except Exception:
        return "es"


def get_spanish_only_disclaimer(detected_lang: str) -> str | None:
    """
    Si el idioma no es español, retorna el mensaje de disculpa en ese idioma.
    Si es español, retorna None.
    """
    if detected_lang == "es":
        return None
    return SPANISH_ONLY_MESSAGES.get(detected_lang, SPANISH_ONLY_MESSAGES["default"])


def parse_llm_response(response: str) -> tuple[str, str]:
    """
    Parsea la respuesta del LLM que incluye el código de idioma al inicio.
    Formato esperado: [xx] texto de respuesta...

    Returns:
        tuple: (idioma, texto_limpio)
        - idioma: código ISO 639-1 (es, en, fr, etc.) o "es" por defecto
        - texto_limpio: respuesta sin el prefijo de idioma
    """
    import re

    if not response:
        return "es", ""

    # Buscar patrón [xx] al inicio (con posibles espacios)
    match = re.match(r'^\s*\[([a-z]{2})\]\s*', response, re.IGNORECASE)

    if match:
        idioma = match.group(1).lower()
        texto_limpio = response[match.end():].strip()
        return idioma, texto_limpio

    # Si no tiene el prefijo, retornar "es" por defecto
    return "es", response.strip()
