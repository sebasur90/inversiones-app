#!/usr/bin/env bash
# Watchdog de diagnóstico: sondea la app a través de nginx y, cuando falla o se pone lenta,
# vuelca evidencia del estado del sistema a un log. NO reinicia nada: sólo observa y registra.
#
# Uso en el servidor:
#   chmod +x scripts/watchdog.sh
#   nohup ./scripts/watchdog.sh > /dev/null 2>&1 &
#
# Cuando la web vuelva a colgarse, mirar:  tail -100 /var/log/inversiones-watchdog.log

set -u

URL="${URL:-http://localhost:8087/api/inversiones/carteras}"
LOG="${LOG:-/var/log/inversiones-watchdog.log}"
INTERVALO="${INTERVALO:-30}"     # segundos entre sondas
LENTO="${LENTO:-10}"             # segundos: por encima de esto se considera degradado
TIMEOUT="${TIMEOUT:-25}"         # corte de la sonda

# Nombres de los contenedores (se detectan una vez al arrancar).
BACK=$(docker ps --format '{{.Names}}' | grep -i 'backend' | head -1)
FRONT=$(docker ps --format '{{.Names}}' | grep -i 'frontend' | head -1)

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

evidencia() {
    local motivo="$1"
    log "═══════════════════════════════════════════════════════"
    log "INCIDENTE: $motivo"

    log "--- contenedores ---"
    docker ps --format 'table {{.Names}}\t{{.Status}}' >> "$LOG" 2>&1

    log "--- recursos (CPU/memoria) ---"
    docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}' >> "$LOG" 2>&1

    log "--- memoria del host ---"
    free -m >> "$LOG" 2>&1

    log "--- disco ---"
    df -h / >> "$LOG" 2>&1

    log "--- threads del backend ---"
    docker top "$BACK" >> "$LOG" 2>&1

    # ¿El backend responde saltándose nginx? Distingue "backend trabado" de "nginx roto".
    log "--- /health directo al backend (sin nginx) ---"
    timeout 15 docker exec "$BACK" python -c \
        "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/health',timeout=10).read())" \
        >> "$LOG" 2>&1 || log "  (el backend NO respondió su propio /health -> está trabado por dentro)"

    log "--- conexiones abiertas hacia el backend ---"
    docker exec "$BACK" python -c "
import subprocess
try:
    print(subprocess.run(['ss','-tan'],capture_output=True,text=True).stdout[:3000])
except Exception as e:
    print('ss no disponible:', e)
" >> "$LOG" 2>&1

    log "--- últimas 60 líneas del backend ---"
    docker logs --tail 60 "$BACK" >> "$LOG" 2>&1

    log "--- últimas 30 líneas de nginx ---"
    docker logs --tail 30 "$FRONT" >> "$LOG" 2>&1

    log "--- OOM kills recientes en el host ---"
    dmesg -T 2>/dev/null | grep -i "killed process\|out of memory" | tail -5 >> "$LOG" 2>&1

    log "═══════════════════════════════════════════════════════"
}

log "watchdog iniciado (backend=$BACK frontend=$FRONT url=$URL)"

fallando=0
while true; do
    inicio=$(date +%s)
    codigo=$(curl -s -o /dev/null -w '%{http_code}' --max-time "$TIMEOUT" "$URL" 2>/dev/null)
    fin=$(date +%s)
    duracion=$((fin - inicio))

    if [ "$codigo" != "200" ]; then
        if [ "$fallando" -eq 0 ]; then
            evidencia "sonda FALLÓ (http=$codigo, ${duracion}s)"
            fallando=1
        fi
    elif [ "$duracion" -ge "$LENTO" ]; then
        log "DEGRADADO: la sonda tardó ${duracion}s (http=$codigo)"
    else
        if [ "$fallando" -eq 1 ]; then
            log "RECUPERADO tras el incidente (http=$codigo, ${duracion}s)"
            fallando=0
        fi
    fi

    sleep "$INTERVALO"
done
