#!/bin/bash
# =============================================================
# Orquestador - Script de inicializacion
# =============================================================
# Inicializa el stack de orquestacion multicanal
# =============================================================

set -e

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Directorio del script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=============================================="
echo "  Orquestador - Inicializacion"
echo "=============================================="
echo ""

# 1. Cargar o crear .env
if [ -f .env ]; then
    log_info "Cargando variables de .env"
    source .env
else
    if [ -f .env.example ]; then
        log_warn "No existe .env, creando desde .env.example"
        cp .env.example .env
        source .env
        log_warn "Edita .env con tus credenciales antes de continuar"
        echo ""
        echo "Valores a configurar:"
        echo "  - EVOLUTION_API_KEY: API Key de Evolution (mensajeria/.env)"
        echo ""
        read -p "Presiona Enter para continuar o Ctrl+C para cancelar..."
    else
        log_error "No existe .env ni .env.example"
        exit 1
    fi
fi

# 2. Crear directorios de datos
log_info "Creando directorios de datos..."
mkdir -p stack_data/redis
mkdir -p stack_data/workers/app
log_success "Directorios creados"

# 3. Crear red vpn-proxy si no existe
if ! docker network ls | grep -q vpn-proxy; then
    log_info "Creando red vpn-proxy..."
    docker network create vpn-proxy
    log_success "Red vpn-proxy creada"
else
    log_info "Red vpn-proxy ya existe"
fi

# 4. Construir imagenes
log_info "Construyendo imagenes..."
docker compose build
log_success "Imagenes construidas"

# 5. Iniciar servicios
log_info "Iniciando servicios..."
docker compose up -d
log_success "Servicios iniciados"

# 6. Esperar a que Redis este listo
log_info "Esperando a que Redis este listo..."
for i in {1..30}; do
    if docker exec redis-orquestador redis-cli -a "${REDIS_PASSWORD:-orquestador123}" ping 2>/dev/null | grep -q PONG; then
        log_success "Redis listo"
        break
    fi
    sleep 1
done

# 7. Esperar a que Workers este listo
log_info "Esperando a que Workers este listo..."
for i in {1..60}; do
    if curl -s http://localhost:8000/health >/dev/null 2>&1; then
        log_success "Workers listo"
        break
    fi
    sleep 2
done

# 8. Verificar estado
echo ""
echo "=============================================="
echo "  Estado de los servicios"
echo "=============================================="
docker compose ps

echo ""
echo "=============================================="
echo "  Endpoints disponibles"
echo "=============================================="
echo ""
echo "Workers API:"
echo "  - Health:           http://localhost:8000/health"
echo "  - Chat API:         POST http://localhost:8000/api/chat"
echo "  - WhatsApp Webhook: POST http://localhost:8000/webhook/evolution"
echo "  - Telegram Webhook: POST http://localhost:8000/webhook/telegram (pendiente)"
echo ""
echo "Redis:"
echo "  - URL interna: redis://:${REDIS_PASSWORD:-orquestador123}@redis-orquestador:6379/0"
echo ""

# 9. Verificar conexion con servicios de IA
echo "=============================================="
echo "  Verificando servicios de IA"
echo "=============================================="
echo ""

check_service() {
    local name=$1
    local url=$2
    if curl -s --connect-timeout 5 "$url" >/dev/null 2>&1; then
        log_success "$name disponible en $url"
        return 0
    else
        log_warn "$name no disponible en $url"
        return 1
    fi
}

check_service "STT (Whisper)" "${STT_URL:-http://agente_ia:8001}/health"
check_service "TTS (Coqui)" "${TTS_URL:-http://agente_ia:8002}/health"
check_service "LLM (Ollama)" "${LLM_URL:-http://agente_ia:11434}"
check_service "Evolution API" "${EVOLUTION_URL:-http://evolution:8080}"

echo ""
echo "=============================================="
echo "  Configuracion del Webhook"
echo "=============================================="
echo ""
echo "Para que WhatsApp envie mensajes a este servicio,"
echo "configura el webhook en Evolution API:"
echo ""
echo "  POST ${EVOLUTION_URL:-http://evolution:8080}/webhook/set/whatsapp_main"
echo "  {"
echo "    \"webhook\": {"
echo "      \"enabled\": true,"
echo "      \"url\": \"http://workers:8000/webhook/evolution\","
echo "      \"webhookByEvents\": true,"
echo "      \"webhookBase64\": true,"
echo "      \"events\": [\"MESSAGES_UPSERT\"]"
echo "    }"
echo "  }"
echo ""
echo "Nota: El webhook se configura automaticamente desde mensajeria/init.sh"
echo ""
log_success "Inicializacion completada"
