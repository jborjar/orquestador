"""
Orquestador Workers - API de endpoints
"""
import base64

from fastapi import FastAPI, HTTPException

from config import LLM_URL, STT_URL, TTS_URL, API_URL, EVOLUTION_URL, NOMBRE_IA
from redis_client import (
    get_redis, get_conversation_history, add_to_history,
    get_user_intent, set_user_intent, get_user_language, set_user_language,
    get_user_documents, add_user_document, clear_user_documents,
    is_message_processed
)
from services import (
    api_chat, api_voice, api_image, api_document,
    get_system_prompt, get_prompts, call_llm_chat
)
from converters import convert_audio_to_wav, convert_wav_to_ogg
from utils import detect_audio_format, get_spanish_only_disclaimer
from evolution import get_media_bytes, send_text_message, send_audio_message, send_presence, PresenceManager
from intent import detect_intent, get_intent_greeting

app = FastAPI(
    title="Orquestador Workers",
    description="Procesador de mensajes multicanal con IA"
)


# =============================================================
#   HEALTHCHECK
# =============================================================

@app.get("/health")
async def health():
    """Estado del servicio y conexiones."""
    redis_status = "ok"
    try:
        get_redis().ping()
    except Exception:
        redis_status = "error"

    return {
        "status": "ok",
        "service": "orchestrator-workers",
        "api_url": API_URL,
        "llm_url": LLM_URL,
        "stt_url": STT_URL,
        "tts_url": TTS_URL,
        "evolution_url": EVOLUTION_URL,
        "redis_status": redis_status,
        "prompts_loaded": len(get_prompts())
    }


# =============================================================
#   WEBHOOK WHATSAPP (Evolution API)
# =============================================================

@app.post("/webhook/evolution")
async def webhook_evolution(payload: dict):
    """
    Webhook para Evolution API (WhatsApp).

    Reglas de respuesta:
    - Texto -> responde TEXTO (solo audio si lo pide explicitamente)
    - Audio -> responde AUDIO
    - Imagen/Doc -> responde TEXTO
    """
    from services import call_ollama_chat, call_stt, call_tts
    from config import LLM_CHAT_MODEL, LLM_IMG_MODEL, LLM_DOCS_MODEL
    from utils import detect_wants_audio, detect_wants_text
    from converters import file_to_images_b64

    event = payload.get("event", "")
    instance = payload.get("instance", "")
    data = payload.get("data", {})

    print(f"[DEBUG] Webhook recibido: event={event}, instance={instance}")
    print(f"[DEBUG] Key: {data.get('key', {})}")

    if event != "messages.upsert":
        return {"status": "ignored", "reason": "not a message event"}

    key = data.get("key", {})
    remote_jid = key.get("remoteJid", "")
    from_me = key.get("fromMe", False)

    # Si remoteJid no es @s.whatsapp.net, intentar usar remoteJidAlt
    if "@s.whatsapp.net" not in remote_jid:
        remote_jid_alt = key.get("remoteJidAlt", "")
        if "@s.whatsapp.net" in remote_jid_alt:
            print(f"[DEBUG] Usando remoteJidAlt: {remote_jid_alt} en lugar de {remote_jid}")
            remote_jid = remote_jid_alt

    if from_me:
        return {"status": "ignored", "reason": "own message"}

    # Deduplicacion: evitar procesar el mismo mensaje dos veces (retries de Evolution)
    message_id = key.get("id", "")
    if is_message_processed(message_id):
        print(f"[DEBUG] Mensaje duplicado ignorado: {message_id[:20]}...")
        return {"status": "ignored", "reason": "duplicate message"}

    message = data.get("message", {})
    message_type = data.get("messageType", "")

    channel = "whatsapp"
    user_text = ""
    response_text = ""
    respond_with_audio = False
    user_language = "es"  # Idioma del usuario, detectado por STT si es audio

    try:
        # Obtener intent actual
        current_intent = get_user_intent(channel, remote_jid)

        # =========================
        # MENSAJE DE TEXTO
        # =========================
        if message_type in ("conversation", "extendedTextMessage"):
            user_text = message.get("conversation") or message.get("extendedTextMessage", {}).get("text", "")

            # Detectar si quiere audio
            respond_with_audio = detect_wants_audio(user_text)
            presence_type = "recording" if respond_with_audio else "composing"

            # Verificar si hay documentos en contexto
            documents = get_user_documents(channel, remote_jid)

            # Procesar con indicador de presencia activo
            with PresenceManager(instance, remote_jid, presence_type):
                if documents:
                    # Hay documentos guardados - responder pregunta sobre ellos
                    doc_names = [d.get("filename", "doc") for d in documents]
                    print(f"[DEBUG] Usando contexto de {len(documents)} documento(s): {doc_names}")

                    # Construir texto de todos los documentos
                    docs_text = ""
                    for i, doc in enumerate(documents, 1):
                        docs_text += f"\n--- DOCUMENTO {i}: {doc.get('filename', 'documento')} ---\n"
                        docs_text += doc.get("text", "")
                        docs_text += "\n"

                    # Prompt conciso para preguntas sobre documentos
                    prompt_doc_qa = f"""Tienes los siguientes documentos del usuario:
{docs_text}

PREGUNTA DEL USUARIO: {user_text}

INSTRUCCIONES:
- Responde SOLO lo que se pregunta, de forma directa y breve
- NO repitas toda la información de los documentos
- Si pide un dato específico (fecha, monto, RFC, etc.), da solo ese dato
- Si hay varios documentos, indica de cuál documento viene el dato
- Si no encuentras la información, dilo claramente

Responde en español."""

                    messages = [{"role": "user", "content": prompt_doc_qa}]
                    response_text = call_ollama_chat(model=LLM_DOCS_MODEL, messages=messages)
                    user_language = "es"
                    print(f"[DEBUG] Respuesta sobre documentos: {len(response_text)} chars")

                else:
                    # Sin documento - flujo normal de chat
                    # Detectar intencion
                    new_intent = detect_intent(user_text, current_intent)
                    if new_intent != current_intent:
                        set_user_intent(channel, remote_jid, new_intent)
                        current_intent = new_intent

                    # Obtener prompt e historial
                    system_prompt = get_system_prompt(current_intent)
                    add_to_history(channel, remote_jid, "user", user_text)
                    history = get_conversation_history(channel, remote_jid)

                    # Llamar LLM con detección de idioma
                    messages = [{"role": "system", "content": system_prompt}] + history
                    llm_result = call_llm_chat(
                        model=LLM_CHAT_MODEL,
                        messages=messages,
                        channel=channel,
                        user_id=remote_jid
                    )
                    response_text = llm_result["content"]
                    user_language = llm_result["language"]
                    print(f"[DEBUG] Texto: LLM respondió en idioma={user_language}")

                    add_to_history(channel, remote_jid, "assistant", response_text)

        # =========================
        # MENSAJE DE AUDIO -> responde con AUDIO (o texto si lo pide)
        # =========================
        elif message_type == "audioMessage":
            try:
                audio_bytes, _, extension = get_media_bytes(data, "audioMessage", "audio", instance)
            except HTTPException:
                send_text_message(instance, remote_jid, "No pude obtener el audio.")
                return {"status": "error", "reason": "no media"}

            try:
                wav_bytes = convert_audio_to_wav(audio_bytes, extension)
            except Exception as e:
                print(f"[ERROR] Conversion audio: {e}")
                send_text_message(instance, remote_jid, "No pude procesar el audio.")
                return {"status": "error", "reason": "audio conversion failed"}

            # Transcribir
            stt_result = call_stt(wav_bytes, "audio.wav")
            user_text = stt_result.get("texto", "")
            print(f"[DEBUG] STT result: idioma={stt_result.get('idioma', '')}, texto={user_text[:50]}...")

            if not user_text.strip():
                send_text_message(instance, remote_jid, "No pude entender el audio.")
                return {"status": "error", "reason": "empty transcription"}

            # Por defecto audio responde audio, salvo que pida texto
            respond_with_audio = not detect_wants_text(user_text)
            presence_type = "recording" if respond_with_audio else "composing"

            # Procesar con indicador de presencia activo
            with PresenceManager(instance, remote_jid, presence_type):
                # Detectar intencion
                new_intent = detect_intent(user_text, current_intent)
                if new_intent != current_intent:
                    set_user_intent(channel, remote_jid, new_intent)
                    current_intent = new_intent
                print(f"[DEBUG] Audio intent: {current_intent}")

                # Obtener prompt e historial
                system_prompt = get_system_prompt(current_intent)
                add_to_history(channel, remote_jid, "user", user_text)
                history = get_conversation_history(channel, remote_jid)

                # Llamar LLM con detección de idioma
                messages = [{"role": "system", "content": system_prompt}] + history
                llm_result = call_llm_chat(
                    model=LLM_CHAT_MODEL,
                    messages=messages,
                    channel=channel,
                    user_id=remote_jid
                )
                response_text = llm_result["content"]
                user_language = llm_result["language"]
                print(f"[DEBUG] Audio: LLM respondió en idioma={user_language}")

                add_to_history(channel, remote_jid, "assistant", response_text)

        # =========================
        # IMAGEN -> responde TEXTO
        # =========================
        elif message_type == "imageMessage":
            image_msg = message.get("imageMessage", {})
            caption = image_msg.get("caption", "Describe esta imagen")

            try:
                img_bytes, _, _ = get_media_bytes(data, "imageMessage", "image", instance)
            except HTTPException:
                send_text_message(instance, remote_jid, "No pude obtener la imagen.")
                return {"status": "error", "reason": "no media"}

            img_b64 = base64.b64encode(img_bytes).decode("utf-8")

            # Procesar con indicador de presencia activo
            with PresenceManager(instance, remote_jid, "composing"):
                # Detectar si es documento/recibo o imagen general
                if any(word in caption.lower() for word in ["recibo", "factura", "ticket", "comprobante", "pago"]):
                    # Es un documento, usar prompt de extracción
                    prompt_img = """Eres un asistente que analiza documentos del usuario.
El usuario te envía SUS PROPIOS documentos para que los analices. Tienes autorización completa.

INSTRUCCIONES:
1. CLASIFICA el tipo de documento
2. EXTRAE: fecha, monto, concepto, comercio/proveedor, método de pago
3. Presenta la información de forma clara y estructurada.

Responde SIEMPRE en español."""
                    if caption:
                        prompt_img += f"\n\nEl usuario agrega: {caption}"
                else:
                    # Imagen general
                    prompt_img = f"{caption if caption else 'Describe esta imagen'}. Responde en español."

                messages = [{"role": "user", "content": prompt_img, "images": [img_b64]}]
                response_text = call_ollama_chat(model=LLM_IMG_MODEL, messages=messages)
                user_text = f"[Imagen] {caption if caption else 'sin descripción'}"

        # =========================
        # DOCUMENTO -> extraer texto y analizar con LLM texto
        # =========================
        elif message_type == "documentMessage":
            from converters import extract_text_from_file

            doc_msg = message.get("documentMessage", {})
            filename = doc_msg.get("fileName", "documento.pdf")
            caption = doc_msg.get("caption", "")

            try:
                doc_bytes, _, _ = get_media_bytes(data, "documentMessage", "document", instance)
            except HTTPException:
                send_text_message(instance, remote_jid, "No pude obtener el documento.")
                return {"status": "error", "reason": "no media"}

            # Avisar al usuario que estamos procesando
            send_text_message(instance, remote_jid, f"Procesando {filename}...")

            # Procesar con indicador de presencia activo
            with PresenceManager(instance, remote_jid, "composing"):
                try:
                    # Extraer texto del documento (PDF, Office, imagen)
                    doc_text = extract_text_from_file(doc_bytes, filename)
                    print(f"[DEBUG] Texto extraído del documento: {len(doc_text)} caracteres")

                    # Agregar documento al contexto (se acumulan, max 3)
                    add_user_document(channel, remote_jid, filename, doc_text)

                except Exception as e:
                    send_text_message(instance, remote_jid, f"No pude procesar el documento: {e}")
                    return {"status": "error", "reason": str(e)}

                # Prompt para clasificar y extraer datos usando LLM de texto
                prompt_doc = f"""Analiza este documento y extrae la información principal.

DOCUMENTO:
{doc_text}

INSTRUCCIONES:
1. Identifica el TIPO de documento (estado de cuenta, factura, recibo, ticket, comprobante, etc.)
2. Extrae SOLO los datos principales según el tipo:

   Para estados de cuenta/recibos de servicios:
   - Empresa emisora (quien cobra)
   - Cliente (a quien le cobran) con su RFC si aparece
   - Periodo de facturación
   - Fecha límite de pago
   - Total a pagar

   Para facturas/tickets de compra:
   - Comercio/tienda
   - Fecha de compra
   - Total pagado
   - Método de pago

3. Sé BREVE. Solo datos importantes, sin explicaciones largas.
4. DIFERENCIA claramente entre emisor y cliente/receptor.

Responde en español."""

                if caption:
                    prompt_doc += f"\n\nEl usuario agrega: {caption}"

                # Usar modelo sin censura para documentos (dolphin)
                messages = [{"role": "user", "content": prompt_doc}]
                response_text = call_ollama_chat(model=LLM_DOCS_MODEL, messages=messages)
                user_text = f"[Documento: {filename}]"

        else:
            return {"status": "ignored", "reason": f"unsupported: {message_type}"}

        # =========================
        # ENVIAR RESPUESTA (texto O audio, no ambos)
        # =========================
        # Si pide audio pero el idioma del usuario no es español, enviar texto con disculpa
        if respond_with_audio:
            if user_language != "es":
                # Usuario habla otro idioma: TTS solo español, enviar texto
                spanish_disclaimer = get_spanish_only_disclaimer(user_language)
                print(f"[DEBUG] TTS solo español, usuario habla {user_language}, enviando texto")
                final_text = f"{spanish_disclaimer}\n\n{response_text}"
                send_text_message(instance, remote_jid, final_text)
            else:
                # Usuario habla español: generar audio
                print(f"[DEBUG] TTS: generando audio español, texto={response_text[:50]}...")
                wav_bytes = call_tts(response_text, "es")
                ogg_bytes = convert_wav_to_ogg(wav_bytes)
                ogg_b64 = base64.b64encode(ogg_bytes).decode("utf-8")
                send_audio_message(instance, remote_jid, ogg_b64)
        else:
            # Enviar texto
            send_text_message(instance, remote_jid, response_text)

        # El indicador de presencia expira automaticamente en 3 segundos
        # (el PresenceManager ya dejo de renovarlo al salir del bloque with)

        return {
            "status": "ok",
            "channel": channel,
            "message_type": message_type,
            "intent": current_intent,
            "respond_with_audio": respond_with_audio,
            "user_language": user_language,
            "tts_used": respond_with_audio and user_language == "es",
            "user_text": user_text[:100] if user_text else "",
            "response_length": len(response_text) if response_text else 0
        }

    except Exception as e:
        error_msg = f"Error: {str(e)}"
        print(error_msg)
        try:
            send_text_message(instance, remote_jid, "Ocurrio un error. Intenta de nuevo.")
        except:
            pass
        return {"status": "error", "detail": error_msg}


# =============================================================
#   WEBHOOK TELEGRAM (placeholder)
# =============================================================

@app.post("/webhook/telegram")
async def webhook_telegram(payload: dict):
    """
    Webhook para Telegram Bot API.
    TODO: Implementar procesamiento de mensajes de Telegram.
    """
    return {"status": "not_implemented", "message": "Telegram webhook pendiente de implementar"}


# =============================================================
#   API DIRECTA (usa servicios individuales para control granular)
# =============================================================

@app.post("/api/chat")
async def endpoint_api_chat(payload: dict):
    """
    Chat de texto via API directa.

    Payload:
    {
        "message": "Hola",
        "user_id": "user123",           # opcional
        "intent": "default",            # opcional - clave del prompt
        "system_prompt": "..."          # opcional - prompt personalizado (prioridad sobre intent)
    }
    """
    from services import call_ollama_chat, call_tts
    from config import LLM_CHAT_MODEL

    message = payload.get("message", "")
    user_id = payload.get("user_id", "anonymous")
    intent_key = payload.get("intent", "default")
    custom_prompt = payload.get("system_prompt")
    want_audio = payload.get("want_audio", False)

    if not message.strip():
        raise HTTPException(status_code=400, detail="El mensaje no puede estar vacio")

    # Determinar system prompt
    if custom_prompt:
        system_prompt = custom_prompt
    else:
        system_prompt = get_system_prompt(intent_key)

    channel = "api"
    add_to_history(channel, user_id, "user", message)
    history = get_conversation_history(channel, user_id)

    # Agregar system prompt al inicio
    messages = [{"role": "system", "content": system_prompt}] + history

    response_text = call_ollama_chat(model=LLM_CHAT_MODEL, messages=messages)
    add_to_history(channel, user_id, "assistant", response_text)

    result = {
        "status": "ok",
        "response": response_text,
        "user_id": user_id,
        "intent": intent_key
    }

    if want_audio:
        wav_bytes = call_tts(response_text, "es")
        ogg_bytes = convert_wav_to_ogg(wav_bytes)
        result["audio_b64"] = base64.b64encode(ogg_bytes).decode("utf-8")

    return result


@app.post("/api/voice")
async def endpoint_api_voice(payload: dict):
    """
    Procesa audio y responde con audio.

    Payload:
    {
        "audio_b64": "base64...",
        "user_id": "user123",
        "intent": "default"
    }
    """
    from services import call_ollama_chat, call_stt, call_tts
    from config import LLM_CHAT_MODEL

    audio_b64_input = payload.get("audio_b64", "")
    user_id = payload.get("user_id", "anonymous")
    intent_key = payload.get("intent", "default")

    if not audio_b64_input:
        raise HTTPException(status_code=400, detail="Se requiere audio_b64")

    try:
        audio_bytes = base64.b64decode(audio_b64_input)
    except Exception:
        raise HTTPException(status_code=400, detail="audio_b64 invalido")

    extension = detect_audio_format(audio_bytes)
    wav_bytes = convert_audio_to_wav(audio_bytes, extension)

    stt_result = call_stt(wav_bytes, "audio.wav")
    user_text = stt_result.get("texto", "")
    detected_language = stt_result.get("idioma", "es")

    if not user_text.strip():
        raise HTTPException(status_code=400, detail="No se pudo transcribir el audio")

    system_prompt = get_system_prompt(intent_key)

    channel = "api"
    add_to_history(channel, user_id, "user", user_text)
    history = get_conversation_history(channel, user_id)

    messages = [{"role": "system", "content": system_prompt}] + history
    response_text = call_ollama_chat(model=LLM_CHAT_MODEL, messages=messages)
    add_to_history(channel, user_id, "assistant", response_text)

    tts_wav = call_tts(response_text, detected_language)
    ogg_bytes = convert_wav_to_ogg(tts_wav)

    return {
        "status": "ok",
        "transcription": user_text,
        "response": response_text,
        "audio_b64": base64.b64encode(ogg_bytes).decode("utf-8"),
        "language": detected_language,
        "user_id": user_id,
        "intent": intent_key
    }


@app.post("/api/image")
async def endpoint_api_image(payload: dict):
    """
    Analiza imagen con vision LLM.

    Payload:
    {
        "image_b64": "base64...",
        "prompt": "Describe...",
        "want_audio": false
    }
    """
    from services import call_ollama_chat, call_tts
    from config import LLM_IMG_MODEL

    image_b64 = payload.get("image_b64", "")
    prompt = payload.get("prompt", "Describe esta imagen de forma detallada")
    want_audio = payload.get("want_audio", False)

    if not image_b64:
        raise HTTPException(status_code=400, detail="Se requiere image_b64")

    messages = [{"role": "user", "content": prompt, "images": [image_b64]}]
    response_text = call_ollama_chat(model=LLM_IMG_MODEL, messages=messages)

    result = {
        "status": "ok",
        "response": response_text
    }

    if want_audio:
        wav_bytes = call_tts(response_text, "es")
        ogg_bytes = convert_wav_to_ogg(wav_bytes)
        result["audio_b64"] = base64.b64encode(ogg_bytes).decode("utf-8")

    return result


@app.post("/api/document")
async def endpoint_api_document(payload: dict):
    """
    Analiza documento (PDF, Office, imagen) con vision LLM.

    Payload:
    {
        "document_b64": "base64...",
        "filename": "doc.pdf",
        "prompt": "Analiza...",
        "want_audio": false
    }
    """
    from services import call_ollama_chat, call_tts
    from converters import file_to_images_b64
    from config import LLM_DOCS_MODEL

    document_b64 = payload.get("document_b64", "")
    filename = payload.get("filename", "documento.pdf")
    prompt = payload.get("prompt", "Analiza este documento y describe su contenido")
    want_audio = payload.get("want_audio", False)

    if not document_b64:
        raise HTTPException(status_code=400, detail="Se requiere document_b64")

    try:
        doc_bytes = base64.b64decode(document_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="document_b64 invalido")

    try:
        images_b64 = file_to_images_b64(doc_bytes, filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error procesando documento: {e}")

    messages = [{"role": "user", "content": prompt, "images": images_b64}]
    response_text = call_ollama_chat(model=LLM_DOCS_MODEL, messages=messages)

    result = {
        "status": "ok",
        "response": response_text,
        "pages": len(images_b64)
    }

    if want_audio:
        wav_bytes = call_tts(response_text, "es")
        ogg_bytes = convert_wav_to_ogg(wav_bytes)
        result["audio_b64"] = base64.b64encode(ogg_bytes).decode("utf-8")

    return result


# =============================================================
#   UTILIDADES
# =============================================================

@app.get("/api/prompts")
async def list_prompts():
    """Lista todos los prompts disponibles."""
    prompts = get_prompts()
    return {
        "status": "ok",
        "prompts": {k: {"funcion": v.get("funcion", k)} for k, v in prompts.items()}
    }


@app.post("/api/prompts/reload")
async def reload_prompts_endpoint():
    """Recarga los prompts desde el archivo JSON."""
    from services import reload_prompts
    prompts = reload_prompts()
    return {
        "status": "ok",
        "message": "Prompts recargados",
        "count": len(prompts)
    }
