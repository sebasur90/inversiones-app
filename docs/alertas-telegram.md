# Avisos por Telegram — puesta en marcha

Pasos para activar los avisos al celular. Son de una sola vez: una vez configurado, no hay que
volver acá.

## Qué avisa

| Aviso | De dónde sale el nivel / la regla |
|---|---|
| 🔴 **Stop-loss** de una posición | pestaña `Instrumentos` del Sheet (`stop_loss_modo` / `stop_loss_valor`) |
| 🎯 **Objetivo** de una posición | pestaña `Instrumentos` del Sheet (`objetivo_modo` / `objetivo_valor`) |
| 🟢 **Zona de compra** de la watchlist | el precio de compra que le fijaste al ticker en la Watchlist |
| 🟠 **Señal de venta** de una estrategia | una estrategia de Análisis técnico con "Ventas" prendido |
| 🟢 **Señal de compra** de una estrategia | una estrategia de Análisis técnico con "Compras" prendido |

Los tres primeros vienen prendidos; las estrategias arrancan **todas apagadas** (ver el paso 6).
Todo se configura en **Ajustes → Qué avisar**.

## Cómo se lee un aviso

```
🔔 Alertas de inversiones

🔴 STOP-LOSS — revisar salida
AL30 (Bono AL30) · cartera Principal
USD 95,50 ≤ stop USD 96,00 (-0,5%)
10 un. · PPC USD 100,00 · -4,5%

🟠 SEÑAL DE VENTA — revisar salida
AAPL (Apple) · cartera Principal
RSI sobrecompra · regla de salida
cierre del 06/10: USD 231,40
25 un. · PPC USD 180,00 · +28,6%

🟢 OPORTUNIDAD DE COMPRA — en zona
MSFT (Microsoft) · watchlist
ARS 24.000,00 ≤ objetivo ARS 25.000,00 (-4,0%)

🟢 SEÑAL DE COMPRA
SPY (S&P 500 ETF) · watchlist · ya tenés posición
Cruce de medias 20/50 · entrada
cierre del 06/10: USD 540,10
```

Cada aviso responde, en ese orden: **qué acción implica** (el encabezado), **quién es y de dónde
viene** (cartera X o watchlist, y si ya tenés posición), **qué regla lo disparó** y **cuánto
tenés** (cantidad, precio promedio de compra y resultado actual). El encabezado dice la acción
pero no recomienda ejecutarla: la decisión es tuya.

En las señales el precio dice **"cierre del dd/mm"** y no "precio" porque sale de la serie diaria
(`barras_ohlcv`), que por diseño no coincide con la última cotización de `precios_instrumento`.
Sin esa aclaración verías dos precios distintos del mismo ticker el mismo día.

---

## 1. Crear el bot

En Telegram, buscá **@BotFather** y escribile `/newbot`. Te va a pedir:

1. un nombre cualquiera, por ejemplo `Mis inversiones`;
2. un usuario que termine en `bot`, por ejemplo `sebas_inversiones_bot`.

Te responde con el token, que se ve así:

```
8123456789:AAHk3l-xYzAbCdEfGhIjKlMnOpQrStUvWx
```

Ese es el **`TELEGRAM_BOT_TOKEN`**. Es una credencial: no va a git ni a una captura de pantalla.
Si se filtra, en @BotFather podés revocarlo con `/revoke`.

## 2. Conseguir tu chat id

En Telegram buscá **@userinfobot** y mandale cualquier mensaje. Te contesta con tu `Id`, un número
como `123456789`. Ese es el **`TELEGRAM_CHAT_ID`**.

> Alternativa sin bots de terceros: abrir `https://api.telegram.org/bot<TOKEN>/getUpdates` en el
> navegador (después del paso 3) y buscar `result[0].message.chat.id` en el JSON.

## 3. Hablarle al bot una vez

Buscá tu bot por el usuario que le pusiste y mandale un "hola".

**Este paso es obligatorio.** Telegram no permite que un bot escriba primero a alguien que nunca le
habló: si lo saltás, el envío falla con `chat not found` aunque el token y el id estén bien.

## 4. Completar los dos valores

```
ALERTAS_ENABLED=true
TELEGRAM_BOT_TOKEN=8123456789:AAHk3l-xYzAbCdEfGhIjKlMnOpQrStUvWx
TELEGRAM_CHAT_ID=123456789
```

**¿En qué archivo?** Depende de cómo levantes la app, porque `--env-file` *reemplaza* al `.env` por
defecto en lugar de sumarse:

| Cómo levantás | Archivo que compose lee |
|---|---|
| `docker compose -f docker-compose.yml -f docker-compose.corporate.yml up` | `.env` |
| `./docker-helper.sh corporate up` | `.env.corporate` |

Si usás las dos formas, las líneas van en los dos archivos. Ambos están en `.gitignore`.

## 5. Reiniciar y probar

```bash
docker compose -f docker-compose.yml -f docker-compose.corporate.yml up -d --build backend
```

En la app: **Ajustes → Avisos al celular → "Mandar mensaje de prueba"**. Si llega el mensaje,
terminó la configuración.

## 6. Sembrar el estado antes del primer uso real

Si ya tenés posiciones con el nivel cruzado, la primera evaluación te las manda todas juntas. Para
evitar esa andanada, marcá los cruces actuales como "ya vistos" sin avisar:

```bash
curl -X POST "http://localhost:8087/api/inversiones/alertas/evaluar?notificar=false"
```

Desde ahí en adelante sólo avisa de los cruces **nuevos**.

## 7. Elegir qué estrategias avisan

En **Ajustes → Qué avisar**, cada estrategia guardada tiene dos casillas independientes: *Compras*
y *Ventas*. Arrancan apagadas a propósito — el catálogo siembra 16 presets reusables sobre todo el
universo, y prenderlos todos serían decenas de mensajes por día.

Mientras no haya ninguna prendida, el servidor **ni calcula** las señales: correr los backtests de
todo el universo para después descartarlos sería el gasto más caro del job programado.

Sólo se avisan las señales de las **últimas 2 ruedas**. Una señal de hace una semana ya no es
accionable: el precio se movió.

Después de prender la primera estrategia conviene volver a sembrar con el `curl` del paso 6, por si
hay señales frescas de los últimos días.

## 8. Para que corra solo

En el `.env` del **servidor**:

```
SCHEDULER_ENABLED=true
```

Con eso quedan andando dos tareas, las dos de lunes a viernes:

| Cuándo | Qué hace |
|---|---|
| **11, 13, 15, 17** (la rueda) | refresca sólo las cotizaciones y evalúa las alertas |
| **18:30** (tras el cierre) | sincroniza todo el Sheet y evalúa las alertas |

Por eso los avisos llegan **durante el día**, cada dos horas, y no sólo después del cierre. Los
horarios se cambian con `REFRESCO_HORAS` (vacío desactiva sólo el refresco) y `SCHEDULER_HORA`.

En la máquina de desarrollo dejá `SCHEDULER_ENABLED=false`: cada corrida gasta cupo de la API de
IOL (un sync diario + 4 refrescos por día hábil son ~1.050 llamadas al mes contra el tope de 22.000,
menos del 5%, pero no hace falta gastarlo dos veces).

Para probar el refresco sin esperar al horario:

```bash
curl -X POST http://localhost:8087/api/inversiones/refrescar-precios
```

En Ajustes → "Cotizaciones" se ve cuándo fue el último.

---

## Si algo no funciona

| Mensaje | Qué pasa |
|---|---|
| `chat not found` | Falta el paso 3: hablale al bot desde tu Telegram. |
| `falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID` | El valor no llegó al contenedor. Ver el comando de abajo. |
| `alertas deshabilitadas (ALERTAS_ENABLED)` | Falta `ALERTAS_ENABLED=true` en el archivo que compose lee. |
| `no hubo respuesta de Telegram` | Sin salida a `api.telegram.org`: proxy, DNS o red. |
| `Unauthorized` / `401` | Token mal copiado o revocado. |

Comprobar que las variables llegaron al contenedor:

```bash
docker compose -f docker-compose.yml -f docker-compose.corporate.yml config | grep -E "TELEGRAM|ALERTAS"
```

Ver qué hizo el backend:

```bash
docker compose logs --tail=50 backend | grep -iE "alertas|telegram|scheduler"
```

**Proxy corporativo**: el POST a `api.telegram.org` sale por `HTTP_PROXY`/`HTTPS_PROXY`
(`market_data/client.py` usa `trust_env=True`). Si el proxy bloquea Telegram, la prueba va a fallar
en la máquina de desarrollo pero funcionar en el servidor, que sale directo.

---

## Cómo se comporta (para no confundir un acierto con un error)

- **Un aviso por cruce, no uno por día.** Cada nivel guarda estado (`armada` / `disparada`). Si el
  precio sigue por debajo del stop-loss durante una semana, avisa una sola vez.
- **Se re-arma al alejarse.** La alerta vuelve a quedar lista sólo cuando el precio regresa al otro
  lado del nivel y se aleja más del 2%. Esa banda existe para que un precio oscilando sobre el nivel
  no genere un aviso por corrida.
- **Las señales no usan esa banda** (no hay nivel del cual alejarse): deduplican por la barra de la
  señal. La misma señal aparece durante dos ruedas y sólo la primera avisa; una compra, una venta y
  otra compra del mismo par avisan tres veces porque cada una cae en una barra distinta.
- **Un solo mensaje por corrida**, con todos los avisos agrupados por tipo. Si hay demasiados, el
  mensaje se recorta por avisos enteros y cada bloque conserva su encabezado y su conteo
  (`… y 12 más de este tipo`): nunca se corta a mitad de un aviso.
- **Volver al lado normal no se avisa**: no es noticia.
- **Apagar un tipo de aviso no deja de seguirlo.** El cruce se guarda igual y se silencia, así que
  volver a prenderlo meses después no manda de golpe todo lo que pasó mientras estaba apagado.
- Si el envío falla, el aviso queda pendiente y se reintenta en la corrida siguiente, sin volver a
  tratar el cruce como nuevo. El texto del reintento es **idéntico** al del envío original.

El detalle técnico está en `backend/app/services/alertas_engine.py` y en la sección de
`DESARROLLO.md`.
