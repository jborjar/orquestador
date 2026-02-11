"""
Deteccion de intencion del usuario
Selecciona el prompt adecuado segun el mensaje
"""
import re
from typing import Optional

# Patrones para detectar intencion
INTENT_PATTERNS = {
    "soporte": [
        r"no funciona", r"error", r"problema", r"falla", r"ayuda",
        r"no puedo", r"no sirve", r"bug", r"issue", r"roto",
        r"arreglar", r"reparar", r"solucion", r"tecnico"
    ],
    "ventas": [
        r"comprar", r"precio", r"costo", r"cuanto cuesta", r"cuánto cuesta",
        r"catalogo", r"catálogo", r"productos", r"servicios",
        r"cotizacion", r"cotización", r"descuento", r"promocion", r"promoción",
        r"pagar", r"pago", r"tarjeta", r"factura"
    ],
    "citas": [
        r"cita", r"agendar", r"programar", r"reservar", r"turno",
        r"disponibilidad", r"horario", r"fecha", r"cancelar cita",
        r"reagendar", r"mover cita", r"cuando puedo"
    ],
    "cobranza": [
        r"deuda", r"debo", r"pago pendiente", r"cobro", r"moroso",
        r"recibo", r"vencido", r"atraso", r"pagar deuda"
    ],
    "recepcion": [
        r"hola", r"buenos dias", r"buenos días", r"buenas tardes",
        r"buenas noches", r"quien eres", r"quién eres", r"que puedes hacer",
        r"qué puedes hacer", r"como funciona", r"cómo funciona"
    ],
    "documentos": [
        r"documento", r"pdf", r"archivo", r"analiza", r"revisa",
        r"lee este", r"que dice", r"qué dice", r"resume"
    ],
    "faq": [
        r"pregunta", r"duda", r"informacion", r"información",
        r"donde", r"dónde", r"cuando", r"cuándo", r"como", r"cómo",
        r"que es", r"qué es", r"para que", r"para qué"
    ],
    "traductor": [
        r"traduce\b", r"traducir\b", r"tradúceme", r"traduceme",
        r"tradúcelo", r"traducelo", r"traducción de",
        r"translate\b", r"translation of"
    ]
}

# Frases que indican cambio explicito de contexto
CONTEXT_SWITCH_PATTERNS = {
    "soporte": [r"necesito ayuda tecnica", r"tengo un problema tecnico", r"soporte tecnico"],
    "ventas": [r"quiero comprar", r"me interesa", r"quiero adquirir", r"quisiera cotizar"],
    "citas": [r"quiero agendar", r"necesito una cita", r"puedo hacer una cita"],
    "recepcion": [r"empezar de nuevo", r"reiniciar", r"volver al inicio"],
    "traductor": [r"traduce esto", r"necesito traducir", r"puedes traducir"]
}


def detect_intent(text: str, current_intent: str = "default") -> str:
    """
    Detecta la intencion del usuario basado en el texto.

    Args:
        text: Mensaje del usuario
        current_intent: Intencion actual (para mantener contexto)

    Returns:
        Clave del prompt a usar (default, soporte, ventas, etc.)
    """
    if not text:
        return current_intent

    text_lower = text.lower()

    # 1. Verificar cambio explicito de contexto (alta prioridad)
    for intent, patterns in CONTEXT_SWITCH_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return intent

    # 2. Detectar intencion por patrones
    scores = {}
    for intent, patterns in INTENT_PATTERNS.items():
        score = 0
        for pattern in patterns:
            if re.search(pattern, text_lower):
                score += 1
        if score > 0:
            scores[intent] = score

    # 3. Si hay coincidencias, usar la de mayor score
    if scores:
        best_intent = max(scores, key=scores.get)
        # Solo cambiar si hay suficiente confianza (al menos 2 coincidencias)
        # o si es la primera vez (current_intent es default)
        if scores[best_intent] >= 2 or current_intent == "default":
            return best_intent

    # 4. Mantener contexto actual si no hay cambio claro
    return current_intent


def should_change_intent(text: str, current_intent: str) -> Optional[str]:
    """
    Verifica si el usuario quiere cambiar de contexto explicitamente.
    Retorna el nuevo intent o None si no hay cambio.
    """
    text_lower = text.lower()

    # Detectar si quiere hablar con alguien diferente
    transfer_patterns = {
        "soporte": [r"pasame con soporte", r"hablar con tecnico", r"quiero soporte"],
        "ventas": [r"pasame con ventas", r"hablar con ventas", r"quiero comprar"],
        "default": [r"volver al inicio", r"empezar de nuevo", r"reiniciar conversacion"]
    }

    for intent, patterns in transfer_patterns.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return intent

    return None


def get_intent_greeting(intent: str) -> Optional[str]:
    """
    Retorna un saludo especifico cuando cambia el contexto.
    """
    greetings = {
        "soporte": "Te conecto con soporte técnico. ¿En qué puedo ayudarte?",
        "ventas": "Te paso con el área de ventas. ¿Qué producto o servicio te interesa?",
        "citas": "Perfecto, te ayudo a agendar una cita. ¿Qué fecha y hora prefieres?",
        "cobranza": "Entiendo. Revisemos tu situación de pagos. ¿Me puedes dar tu número de cuenta o identificación?",
        "traductor": None,  # No saludo, traduce directamente
        "default": "¡Hola! ¿En qué puedo ayudarte hoy?"
    }
    return greetings.get(intent)
