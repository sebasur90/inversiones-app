# Ciclos de mercado: lista de verificación (celular y servidor)

Lo que **nunca se vio** en un navegador ni con datos reales. Está en este orden a propósito: primero el servidor (sin él no hay
datos reales), después el celular. Tildá lo que anda y anotá lo que no; con cada ítem roto, copiá el texto o sacá una captura.

Contexto: pantalla `/ciclos` (5 pestañas) y `/ciclos/grupo/:id` (ficha). Doc completa: [ciclos-mercado.md](ciclos-mercado.md).

## 1. Servidor

### 1.1 Despliegue
- [ ] `git pull` y `docker compose up -d --build` (el `--build` no es opcional: cambió el backend y el frontend). Con proxy: `docker compose -f docker-compose.yml -f docker-compose.corporate.yml up -d --build`.
- [ ] El backend arranca sin errores: `docker compose logs backend --tail 50`. Hay migraciones automáticas (columnas `avisar_ciclos` y `ciclos_semilla_en`, tablas `ciclos_avisos_emitidos`, `ciclos_macro_obs`, `ciclos_macro_estado`); no debería quedar ningún error de SQL.
- [ ] Variables del `.env` del servidor: `USE_EXTERNAL_APIS=true`, `SCHEDULER_ENABLED=true` (sin esto no corren los jobs), `CICLOS_HORAS=19` (o la que quieras; vacío lo apaga).
- [ ] `GET /api/inversiones/ciclos/catalogo` responde y `errores` está vacío (el catálogo se lee de `./catalogos`, montado en el contenedor).

### 1.2 Primera descarga (una sola vez, ~2 minutos)
- [ ] `curl -X POST http://localhost:8087/api/inversiones/ciclos/refrescar` → `{"resultado":"iniciado"}`. Esperar y mirar `docker compose logs backend | grep -i ciclos`.
- [ ] `GET /ciclos/estado`: `sin_datos` en 0 (o muy bajo) y `desactualizados` ≤ 1. **Anotá cuáles símbolos no bajaron** (`^MERV` suele llegar atrasado; `BRL=X`, `HKD=X` e `INR=X` tienen huecos): es esperable que el efecto cambiario o el índice local de esos países figure «sin dato».
- [ ] Si Yahoo corta por límite de tasa (`rate_limited` en el log), esperar unos minutos y repetir: lo ya bajado se conserva.
- [ ] `GET /ciclos/regimen`: `estado` = `disponible` o `no_concluyente` (no `no_disponible`), con `falta` vacío o explicado. Es el CSV de FRED: si falla, ver si el servidor llega a `fred.stlouisfed.org`.
- [ ] `GET /ciclos/tasas`: las cuatro tasas con nivel y fecha de los últimos días.

### 1.3 Mi cartera con datos reales
- [ ] `GET /carteras/<tu cartera>/ciclos/cartera`: `total_usd` **coincide con el de Exposición** (mismo criterio de totales; hay un test de equivalencia, pero con datos de juguete).
- [ ] Cada dimensión (sector, región, país) suma 100 %. Lo que no tiene sector, país o región aparece en «Sin sector / Sin país / Sin región», nunca desaparece.
- [ ] Un CEDEAR y su variante en pesos aparecen como **un solo emisor** en `…/ciclos/grupos/<id>/instrumentos`.
- [ ] Los temas (inteligencia artificial, transición energética) incluyen los tickers que esperás y marcan «lista curada».

### 1.4 Avisos por Telegram
- [ ] En el `.env`: `ALERTAS_ENABLED=true` y `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` cargados (los de las otras alertas ya sirven).
- [ ] Ajustes → «Qué avisar»: la casilla **Ciclos de mercado** está prendida.
- [ ] Tras la primera evaluación **no llega ningún mensaje** (siembra el estado actual). El log dice `avisos de ciclos` con `sembrados` > 0.
- [ ] La corrida siguiente (otro día) no repite nada. Cuando algún grupo donde tenés posición confirme un cambio (3 semanas), llega **un solo mensaje** con: grupo, estado anterior → nuevo, referencia, semanas sostenidas, peso en la cartera. Verificá que el peso coincida con la ficha.
- [ ] Apagar la casilla y repetir: no manda, pero tampoco acumula (al prenderla de nuevo no llega una avalancha).

## 2. Celular (el shell mide como máximo 448 px)

Antes de empezar: si ves una versión vieja, es el service worker → Ajustes → Privacidad → **borrar datos offline**.

### 2.1 Panorama
- [ ] **Mapa de rotación:** se ve completo, sin desbordar; las cuatro zonas con su etiqueta; los puntos y las colas se distinguen.
- [ ] Tocar un punto abre su panel; el panel dice el estado **con palabra** (no sólo color) y tiene «Ver ficha completa».
- [ ] Cambiar período, referencia y moneda no rompe el mapa; con pocos grupos los puntos no se tapan entre sí.
- [ ] **Mapa de calor:** se desplaza horizontalmente sin mover toda la página; la primera columna (nombre) queda legible.
- [ ] **Cambios de liderazgo:** sólo cambios confirmados.
- [ ] **Régimen macroeconómico:** la tarjeta se abre; muestra los dos ejes con cada serie (valor de hoy, hace 3 meses, cambio y voto) y el contexto aparte. Leer que **no sugiere comprar ni vender**. Si el régimen es «Reflación» con cambios mínimos, el tamaño del cambio se ve.

### 2.2 Sectores y activos / Regiones
- [ ] Las tarjetas muestran estado con palabra, rendimiento y referencia; commodities separados de los sectores.
- [ ] **Regiones:** ficha de un país con la descomposición (ETF en USD / índice local / efecto cambiario) y «sin dato» donde falta, con su motivo.

### 2.3 Relaciones
- [ ] **Matriz de correlaciones:** desplaza sin romper el layout; cada celda dice cuántas observaciones tiene.
- [ ] **Tasas de interés:** las tarjetas se ven en 2 columnas (o 1 en pantallas angostas), los cambios en «pp», el gráfico legible, la curva «normal» o «invertida» con palabra. Cambiar 1A / 5A / 10A / Todo.
- [ ] **Adelantos y rezagos:** elegir «Tasa a 10 años → financieras»; el gráfico de barras se ve y dice que es una hipótesis estadística.

### 2.4 Ficha de un grupo (`/ciclos/grupo/:id`)
- [ ] Gráfico base 100, historial de rotación, período histórico a elegir.
- [ ] **Qué pasó después de cada estado:** los tres selectores (este grupo / todos los de su tipo; mientras está en el estado / al confirmarse; 4, 13, 26 semanas) caben en la pantalla. Con pocos episodios la tarjeta dice «no alcanza para resumir» y **no muestra cifras**. Leer que describe el pasado.
- [ ] **En tu cartera:** posiciones del grupo con sus pesos.

### 2.5 Mi cartera
- [ ] Capital por estado del ciclo (los porcentajes de cada dimensión suman 100 %).
- [ ] Instrumentos de un grupo.
- [ ] **Simulador de rotación:** trasladar un porcentaje de un grupo a otro muestra emisor, instrumento, sector, país y región antes y después, y **no guarda nada** (recargar y verificar que la cartera no cambió).
- [ ] **Modo privacidad** (ojo del header): con la privacidad prendida, los importes de la cartera quedan tapados en esta pestaña y en el simulador.

### 2.6 General
- [ ] Ayuda contextual: abrir un par de «?» (cambio confirmado, episodio, pendiente de la curva, régimen) y la guía de la pantalla.
- [ ] Ningún texto de la pantalla dice «comprar», «vender» ni «recomendado» en el sentido de una indicación.
- [ ] Sin scroll horizontal de toda la página (sólo dentro de las tablas que lo necesitan).
- [ ] Ajustes → «Qué avisar» muestra la casilla «Ciclos de mercado» con su ayuda.

## 3. Qué hacer con lo que falle

| Síntoma | Probable causa |
|---|---|
| Un símbolo sin datos en `/ciclos/estado` | Yahoo no lo devolvió: ver `activo: false` + `nota` en `catalogos/ciclos_grupos.json` (no hace falta rebuild) |
| `/ciclos/regimen` en `no_disponible` | FRED no responde desde el servidor, o `USE_EXTERNAL_APIS=false` |
| El panel/layout se corta en el celular | Anotá el ancho y la pantalla: el shell mide 448 px y las tablas anchas deben desplazarse dentro de su caja |
| Cifras de «Mi cartera» que no coinciden con Exposición | Comparar el `total_usd` de ambas; las posiciones sin cotización entran al costo y la pantalla lo avisa |
| No llega el aviso de Telegram | `ALERTAS_ENABLED`, token y chat id; ver `docker compose logs backend | grep -i "ciclos"`. Un cambio que empezó hace más de 35 días no se avisa a propósito |
