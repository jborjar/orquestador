"""
Configuracion del orquestador - Variables de entorno
"""
import os

# URLs de servicios de IA
API_URL = os.getenv("API_URL", "http://agente_ia:8000")  # API unificada
LLM_URL = os.getenv("LLM_URL", "http://agente_ia:11434")
STT_URL = os.getenv("STT_URL", "http://agente_ia:8001")
TTS_URL = os.getenv("TTS_URL", "http://agente_ia:8002")

# Modelos de Ollama
LLM_CHAT_MODEL = os.getenv("LLM_CHAT_MODEL", "qwen2.5:7b")
LLM_IMG_MODEL = os.getenv("LLM_IMG_MODEL", "llava:7b")
LLM_DOCS_MODEL = os.getenv("LLM_DOCS_MODEL", "llava:7b")

# Evolution API
EVOLUTION_URL = os.getenv("EVOLUTION_URL", "http://evolution:8080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")

# Bot
NOMBRE_IA = os.getenv("NOMBRE_IA", "Asistente")

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://redis-orquestador:6379/0")
MAX_HISTORY = 20
HISTORY_TTL = 86400 * 7  # 7 dias

# Extensiones soportadas
OFFICE_EXTENSIONS = {".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt", ".odt", ".ods", ".odp"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
