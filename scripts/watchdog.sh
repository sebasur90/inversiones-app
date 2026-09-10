#!/usr/bin/env bash
# Watchdog de diagnóstico para los cuelgues de la web (contenedor en Up, app muda).
#
# Pensado para operarse desde el celular por SSH: comandos cortos, y la captura de evidencia
# —incluido el volcado de stacks del backend— es automática. NO reinicia nada: sólo observa.
#
#   ./scripts/watchdog.sh instalar   Instala y arranca el servicio (sobrevive reboots y cierres de SSH)
#   ./scripts/watchdog.sh ver        Muestra el último incidente capturado
#   ./scripts/watchdog.sh ahora      Captura evidencia en este instante
#   ./scripts/watchdog.sh estado     ¿Está corriendo? ¿Cuántos incidentes van?
#   ./scripts/watchdog.sh red        Diagnostica por qué el puerto no se alcanza desde la red
#   ./scripts/watchdog.sh parar      Detiene el servicio
#
# Atajo recomendado en el servidor (una sola vez):
#   echo "alias w='~/inversiones-app/scripts/watchdog.sh'" >> ~/.bashrc && source ~/.bashrc
# Después alcanza con:  w ver

set -u

URL="${URL:-http://localhost:8087/api/inversiones/carteras}"
LOG="${LOG:-/var/log/inversiones-watchdog.log}"
INTERVALO="${INTERVALO:-30}"     # segundos entre sondas
LENTO="${LENTO:-10}"             # segundos: por encima de esto se considera degradado
TIMEOUT="${TIMEOUT:-25}"         # corte de la sonda
SERVICIO="inversiones-watchdog"
SCRIPT="$(readlink -f "$0")"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

# Los nombres se resuelven en cada uso, no una vez al arrancar: si un contenedor se recrea
# durante el incidente, el watchdog lo sigue encontrando.
backend()  { docker ps --format '{{.Names}}' | grep -i 'backend'  | head -1; }
frontend() { docker ps --format '{{.Names}}' | grep -i 'frontend' | head -1; }

# ── Captura de evidencia ─────────────────────────────────────────────────────
evidencia() {
    local motivo="$1"
    local back front
    back=$(backend); front=$(frontend)

    log "═══════════════════════════════════════════════════════"
    log "INCIDENTE: $motivo"

    # ── Lo más importante primero: en qué está trabado el backend ────────────
    # SIGUSR1 hace que faulthandler (registrado en app/main.py) vuelque el stack de todos los
    # threads a stderr, o sea a `docker logs`. No mata el proceso.
    if [ -n "$back" ]; then
        log "--- volcado de stacks de todos los threads (SIGUSR1) ---"
        local marca
        marca=$(docker logs --tail 1 "$back" 2>&1 | tail -1)
        docker kill -s USR1 "$back" >/dev/null 2>&1 \
            && sleep 3 \
            && docker logs --tail 250 "$back" >> "$LOG" 2>&1 \
            || log "  (no se pudo enviar la señal; ¿el backend fue reconstruido con faulthandler?)"
        [ -n "$marca" ] && log "  (nota: el volcado son las líneas posteriores a: ${marca:0:80})"
    else
        log "  ¡NO HAY CONTENEDOR BACKEND CORRIENDO!"
    fi

    # ── ¿El backend responde salteando nginx? Distingue trabado de inalcanzable ──
    log "--- /health directo al backend, sin pasar por nginx ---"
    if [ -n "$back" ]; then
        timeout 15 docker exec "$back" python -c \
            "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/health',timeout=10).read())" \
            >> "$LOG" 2>&1 \
            || log "  NO RESPONDIÓ -> el backend está trabado por dentro (no es culpa de nginx)"
    fi

    log "--- contenedores ---"
    docker ps --format 'table {{.Names}}\t{{.Status}}' >> "$LOG" 2>&1

    log "--- recursos ---"
    docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}' >> "$LOG" 2>&1

    log "--- memoria del host ---"
    free -m >> "$LOG" 2>&1

    log "--- disco ---"
    df -h / >> "$LOG" 2>&1

    log "--- threads del backend ---"
    [ -n "$back" ] && docker top "$back" >> "$LOG" 2>&1

    log "--- últimas 30 líneas de nginx ---"
    [ -n "$front" ] && docker logs --tail 30 "$front" >> "$LOG" 2>&1

    log "--- OOM kills recientes en el host ---"
    dmesg -T 2>/dev/null | grep -i "killed process\|out of memory" | tail -5 >> "$LOG" 2>&1

    log "FIN DEL INCIDENTE"
    log "═══════════════════════════════════════════════════════"
}

# ── Bucle de sondeo ──────────────────────────────────────────────────────────
vigilar() {
    log "watchdog iniciado (url=$URL, sonda cada ${INTERVALO}s)"
    local fallando=0
    while true; do
        local inicio fin duracion codigo
        inicio=$(date +%s)
        codigo=$(curl -s -o /dev/null -w '%{http_code}' --max-time "$TIMEOUT" "$URL" 2>/dev/null)
        fin=$(date +%s)
        duracion=$((fin - inicio))

        if [ "$codigo" != "200" ]; then
            # Sólo captura en el flanco: un cuelgue de horas deja un incidente, no cientos.
            if [ "$fallando" -eq 0 ]; then
                evidencia "sonda FALLÓ (http=$codigo, ${duracion}s)"
                fallando=1
            fi
        elif [ "$duracion" -ge "$LENTO" ]; then
            log "DEGRADADO: la sonda tardó ${duracion}s (http=$codigo)"
        elif [ "$fallando" -eq 1 ]; then
            log "RECUPERADO solo, sin intervención (http=$codigo, ${duracion}s)"
            fallando=0
        fi

        sleep "$INTERVALO"
    done
}

# ── Subcomandos ──────────────────────────────────────────────────────────────
# Sin argumentos se muestra la ayuda, NO el bucle de sondeo: escribir `w` de más en el celular no
# debe dejar la terminal colgada. El servicio de systemd pasa `vigilar` explícito.
case "${1:-ayuda}" in
    instalar)
        cat > "/etc/systemd/system/${SERVICIO}.service" <<EOF
[Unit]
Description=Watchdog de diagnóstico de inversiones-app
After=docker.service

[Service]
ExecStart=$SCRIPT vigilar
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
        systemctl daemon-reload
        systemctl enable --now "$SERVICIO"
        echo "✓ Watchdog instalado y corriendo. Sobrevive reboots y cierres de SSH."
        echo "  Ver incidentes:  $0 ver"
        ;;

    ver)
        if [ ! -f "$LOG" ]; then echo "Todavía no hay log en $LOG"; exit 0; fi
        # Muestra desde el último "INCIDENTE:" en adelante.
        local_inicio=$(grep -n "INCIDENTE:" "$LOG" | tail -1 | cut -d: -f1)
        if [ -z "$local_inicio" ]; then
            echo "Sin incidentes registrados todavía. Últimas líneas:"
            tail -20 "$LOG"
        else
            echo "═══ Último incidente (línea $local_inicio de $LOG) ═══"
            tail -n "+$((local_inicio - 1))" "$LOG"
        fi
        ;;

    ahora)
        evidencia "captura manual pedida desde la consola"
        echo "✓ Evidencia capturada. Mostrando:"
        "$0" ver
        ;;

    estado)
        systemctl is-active "$SERVICIO" >/dev/null 2>&1 \
            && echo "✓ Watchdog CORRIENDO" \
            || echo "✗ Watchdog DETENIDO (arrancalo con: $0 instalar)"
        if [ -f "$LOG" ]; then
            echo "  Incidentes registrados: $(grep -c 'INCIDENTE:' "$LOG")"
            echo "  Último movimiento: $(tail -1 "$LOG")"
        fi
        ;;

    red)
        # Por qué el servicio no se alcanza desde la red aunque responda en localhost.
        # Todo en una sola corrida: desde el celular no se tipean diez comandos.
        PUERTO="${PUERTO:-8087}"
        echo "═══ DIAGNÓSTICO DE RED (puerto $PUERTO) ═══"

        echo
        echo "── 1. IPs de este host ──"
        ip -4 -o addr show 2>/dev/null | awk '{print "   "$2": "$4}' || hostname -I

        echo
        echo "── 2. ¿Está corriendo el frontend y con qué mapeo? ──"
        docker ps -a --format '   {{.Names}} | {{.Status}} | {{.Ports}}' | grep -i 'frontend' \
            || echo "   ✗ NO HAY CONTENEDOR FRONTEND (¿lo frenó el depends_on service_healthy?)"

        echo
        echo "── 3. ¿En qué interfaz escucha el puerto? ──"
        echo "   (0.0.0.0 o * = todas, bien | 127.0.0.1 = SÓLO LOCAL, ese es el problema)"
        ss -tlnp 2>/dev/null | grep ":$PUERTO" | sed 's/^/   /' \
            || netstat -tlnp 2>/dev/null | grep ":$PUERTO" | sed 's/^/   /' \
            || echo "   ✗ NADIE ESCUCHA EN $PUERTO"

        echo
        echo "── 4. ¿Responde? ──"
        for destino in "127.0.0.1" $(hostname -I 2>/dev/null); do
            codigo=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://$destino:$PUERTO/" 2>/dev/null)
            [ "$codigo" = "200" ] && echo "   ✓ $destino:$PUERTO -> $codigo" \
                                  || echo "   ✗ $destino:$PUERTO -> ${codigo:-sin respuesta}"
        done

        echo
        echo "── 5. Firewall ──"
        echo "   iptables INPUT policy: $(iptables -S INPUT 2>/dev/null | head -1)"
        echo "   iptables FORWARD policy: $(iptables -S FORWARD 2>/dev/null | head -1)"
        echo "   (FORWARD en DROP rompe los puertos publicados por Docker desde otras interfaces)"
        if command -v ufw >/dev/null 2>&1; then
            echo "   ufw:"; ufw status 2>/dev/null | head -12 | sed 's/^/     /'
        fi

        echo
        echo "── 6. Comparación: TODOS los puertos publicados por Docker ──"
        echo "   (comparar el mapeo de los servicios que SÍ se alcanzan contra este)"
        docker ps --format '   {{.Names}} | {{.Ports}}'

        echo
        echo "── 7. Tailscale ──"
        if command -v tailscale >/dev/null 2>&1; then
            echo "   IP tailscale: $(tailscale ip -4 2>/dev/null | head -1)"
            echo "   Rutas anunciadas por este host:"
            tailscale status --json 2>/dev/null | grep -i "advertise\|AllowedIPs" | head -5 | sed 's/^/     /'
            echo "   (si este host NO anuncia 192.168.1.0/24, desde Tailscale hay que entrar"
            echo "    por la IP 100.x, no por la 192.168.x)"
        else
            echo "   tailscale no está instalado en este host"
        fi
        echo
        echo "═══ FIN ═══"
        ;;

    parar)
        systemctl disable --now "$SERVICIO" && echo "✓ Watchdog detenido."
        ;;

    vigilar) vigilar ;;

    ayuda|-h|--help)
        echo "Watchdog de diagnóstico de inversiones-app"
        echo
        echo "  instalar   Instala y arranca el servicio (sobrevive reboots y cierres de SSH)"
        echo "  ver        Muestra el último incidente capturado"
        echo "  ahora      Captura evidencia en este instante"
        echo "  estado     ¿Está corriendo? ¿cuántos incidentes van?"
        echo "  red        Diagnostica por qué el puerto no se alcanza desde la red"
        echo "  parar      Detiene el servicio"
        ;;

    *)
        echo "Subcomando desconocido: $1"
        echo "Uso: $0 {instalar|ver|ahora|estado|red|parar}"
        exit 1
        ;;
esac
