# Guía de Desarrollo - Inversiones App

## Modos de Ejecución

La aplicación puede ejecutarse en dos modos:

### 1. **Modo Local (Excel)** - Para desarrollo en smoa7001lx
```
USE_LOCAL_SHEET=true
```
- Lee datos desde `sheet_local/sheet_inversiones.xlsx`
- No requiere conexión a Google Sheets API
- Ideal para desarrollo cuando hay limitaciones de proxy corporativo
- **Actualmente configurado por defecto en docker-compose.yml**

### 2. **Modo Google Sheets** - Para producción
```
USE_LOCAL_SHEET=false
```
- Lee datos directamente desde Google Sheets
- Requiere:
  - Archivo de credenciales en `credentials/google-service-account.json`
  - Conexión a internet sin bloqueos de proxy

## Cambiar Modo de Operación

### Para usar Google Sheets:
1. Editar `docker-compose.yml`
2. Cambiar: `- USE_LOCAL_SHEET=true` → `- USE_LOCAL_SHEET=false`
3. Reconstruir: `docker compose down && docker compose up -d --build`

### Para usar Excel local (default):
- Todo ya está configurado, solo ejecutar:
  ```bash
  docker compose up
  ```

## Estructura de Archivos

```
inversiones-app/
├── sheet_local/
│   └── sheet_inversiones.xlsx    # Datos locales (3 hojas + opcionales)
│       ├── Movimientos           # Transacciones
│       ├── Instrumentos          # Metadata de tickers
│       ├── Precios               # Series históricas
│       ├── Objetivos             # Opcional: metas financieras por cartera
│       ├── Rebalanceo            # Opcional: % objetivo de asignación
│       ├── Benchmarks            # Opcional: series de benchmarks (además de los automáticos)
│       ├── Configuracion         # Opcional: benchmark/pesos objetivo por cartera
│       └── Tipos de Cambio       # Opcional: CER/MEP dedicados (Fecha, Tipo, Valor)
├── catalogos/
│   └── iol_catalogo.json         # Catálogo de símbolos de IOL, para la Watchlist (ver más abajo)
├── credentials/
│   ├── google-service-account.json  # Para modo Google Sheets
│   └── iol.json                     # Opcional: API de IOL (ver "Precios: IOL" más abajo)
└── backend/
    └── app/services/
        ├── sheets_client.py       # Implementación (detecta USE_LOCAL_SHEET)
        └── market_data/           # APIs externas gratuitas (detecta USE_EXTERNAL_APIS)
```

## CER/MEP y benchmarks automáticos (USE_EXTERNAL_APIS)

```
USE_EXTERNAL_APIS=true   # default en docker-compose.yml y docker-compose.corporate.yml
```

Con el flag prendido, el sync completa automáticamente lo que el Sheet no cubre, usando APIs
gratuitas y sin API key (ver `backend/app/services/market_data/`):

- **CER/MEP diario**: [ArgentinaDatos](https://argentinadatos.com/docs/) (índice UVA como
  deflactor equivalente al CER, y dólar MEP histórico). Antes, si faltaba el MEP de una fecha
  el movimiento se descartaba en silencio; con la serie diaria eso deja de pasar.
- **Benchmark "Inflación (INDEC)"**: índice mensual construido por interés compuesto sobre la
  inflación publicada por ArgentinaDatos. Activa Performance relativa, Comparar benchmarks y el
  Sharpe de Riesgo con un benchmark real además de Dólar (MEP) e Inflación (CER).
- **Precios de renta fija** (bonos soberanos, ONs, letras/LECAPs): [data912](https://data912.com)
  (`/live/arg_bonds`, `/live/arg_corp`, `/live/arg_notes`), vía
  `market_data/data912.py` + `market_data/precios.py`. El match Sheet↔data912 es por símbolo
  exacto; los no encontrados quedan como info en Calidad de datos (nunca se adivina). data912
  cotiza por lámina de 100 VN y el Sheet por 1 VN: la escala se calibra **por ticker**
  comparando la cotización de la API contra el último precio manual del Sheet (factor ≈100 o
  ≈1); cualquier otro ratio no se carga y se reporta. Sólo se agrega el precio **del día**
  (data912 `/live/*` es una foto intradiaria, no una serie); las filas `fuente='api'` van
  acumulando histórico día a día. Si no hay precio previo en el Sheet para un ticker, no se
  carga hasta tener esa referencia.

**El Sheet siempre gana para CER/MEP y Benchmarks**: estos dos valores sólo completan huecos,
nunca pisan una fecha que ya esté cargada a mano (en `Movimientos`, `Precios`, `Tipos de Cambio`
o `Benchmarks`). Si la API no responde (proxy caído, sin internet), el sync no falla: queda una
advertencia en Calidad de datos y se preserva lo último que sí se pudo traer. Para apagarlo
(comportamiento 100% manual, como antes), `USE_EXTERNAL_APIS=false`.

Los **precios de instrumentos** son la excepción: ver la sección siguiente, la precedencia ahí es
distinta (IOL puede pisar al Sheet).

No se automatizaron MERVAL, S&P 500 ni una tasa libre de riesgo histórica: no encontramos una
API gratuita y confiable con esas series (Stooq bloquea el acceso programático con un desafío
JS, y no hay endpoint público con el nivel histórico del MERVAL). Para esos casos seguí
cargando la pestaña `Benchmarks` a mano.

## Precios: IOL como fuente primaria (con fallback a data912/analisistecnico)

Desde que la cuenta tiene credenciales de IOL configuradas (`credentials/iol.json`, ver
`CREDENTIALS.md`), la precedencia por `(ticker, fecha)` para **precios de instrumentos** es:

```
iol > sheet > api
```

- **IOL** es la fuente primaria: `market_data/iol.py` trae el precio del día vía paneles
  (`GET /api/v2/Cotizaciones/{instrumento}/{panel}/{pais}`, una llamada trae docenas de
  símbolos) para renta fija, renta variable y FCI. Si IOL cotiza una fecha que el Sheet
  también cubre, **IOL gana** — el precio manual queda desplazado y se reporta en Calidad de
  Datos (`precio_manual_reemplazado_por_iol`), nunca en silencio.
- El **Sheet** sigue siendo necesario para lo que IOL no cotiza (fondos propios, instrumentos
  ilíquidos, etc.) y para movimientos.
- **data912/analisistecnico** (`fuente='api'`) quedan como red de contención: sólo entran para
  un ticker que IOL no cubrió esa corrida (caída, sin cupo, o sin ese símbolo), y nunca pisan una
  fecha que el Sheet ya trae (ahí sólo IOL puede hacerlo).
- El backfill histórico usa primero analisistecnico (soberanos/letras/CER) y después IOL para lo
  que analisistecnico no cubre: ONs corporativas y renta variable (acciones/CEDEARs), que antes
  no tenían ninguna fuente de historia.
- La columna `fuente` de `precios_instrumento` ahora tiene tres valores: `sheet` | `iol` | `api`.

**Cupo mensual**: la API de IOL bonifica 25.000 llamadas por mes calendario; pasado eso cobra por
bloque adicional. Como los paneles traen docenas de símbolos por llamada, un sync típico gasta
~10 llamadas (1 token + ~9 paneles) en régimen normal; mientras hay historia pendiente de bajar
suma hasta 15 llamadas de backfill de valuación (`fetch_backfill_iol`), 8 de backfill OHLCV de
watchlist (`fetch_backfill_ohlcv_watchlist`) y hasta 20 de cotización suelta de símbolos de la
watchlist que los paneles no cubren (`fetch_precios_watchlist_catalogo`) — pico de ~53 por corrida. El contador (tabla
`estado_api_iol`, persistido en el volumen `backend_data`) corta las llamadas a IOL al llegar a
`IOL_LIMITE_MENSUAL` (default 22.000, ~12% de colchón bajo el límite real) y cae a data912 por el
resto del mes. `IOL_ENABLED=false` apaga sólo IOL sin tocar data912/analisistecnico.

**Tope por corrida**: además del piso mensual, `IOL_MAX_LLAMADAS_POR_SYNC` (default 60) corta las
llamadas de IOL dentro de un mismo sync — colchón para que un solo sync, o una ráfaga de re-syncs
manuales durante la convergencia del backfill, no se coma el cupo del mes sin que nadie lo note.
Al alcanzarlo la corrida cae a data912/analisistecnico y reintenta el resto el próximo sync.
`0` deshabilita esta cota. El análisis técnico (`/api/inversiones/tecnico/*`, serie, indicadores,
backtest) **no** consume cupo: lee sólo de `serie_ohlcv`/`precios_instrumento` en la DB; todo el
gasto de IOL ocurre en el sync que puebla esas tablas.

**Visibilidad**: cada `POST /api/inversiones/sync` devuelve `iol_llamadas` (lo que gastó esa
corrida), `iol_llamadas_mes` e `iol_limite_mes`. `GET /api/inversiones/iol/estado` da el mismo
acumulado del mes (con `restante` contra el cupo) sin necesidad de correr un sync.

Sin `credentials/iol.json` (o con `IOL_ENABLED=false`), la integración con IOL simplemente no
hace ninguna llamada — el comportamiento es el mismo de antes (data912/analisistecnico completan
huecos, el Sheet siempre gana).

## Sincronización en la UI

Independientemente del modo:
- Click en "Sincronizar" lee los datos
- POST `/api/inversiones/sync`
- Timeouts configurados a 300s (5 min) para operaciones largas

## Notas

- El archivo Excel debe tener las mismas 3 hojas: Movimientos, Instrumentos, Precios
- Las columnas deben coincidir exactamente con el Google Sheet original
- En modo local no se requiere acceso a internet

## Modelo de amenaza (decisión explícita, no es deuda)

**La API del backend no tiene autenticación, a propósito.** Es una PWA de un solo usuario que
corre en una LAN de confianza; agregar login/tokens no compra nada acá y sí agrega fricción. No
re-abrir esto como si fuera un descuido.

Consecuencias operativas a tener presentes si algún día esto cambia de contexto:

- **`POST /api/inversiones/sync` sin auth gasta cupo de IOL.** Cualquiera que llegue al puerto del
  backend puede disparar syncs y quemar el cupo mensual bonificado (ver "Cupo mensual" arriba).
  Por eso la app **no debe publicarse fuera de la LAN** sin revisar antes este punto (poner auth,
  o al menos un rate-limit / mutex en el endpoint — el mutex ya está, ver
  `routers/inversiones.py`).
- **El resto de los endpoints exponen la cartera entera en lectura** (montos, movimientos,
  tickers). Mismo criterio: LAN de confianza.
- **El laboratorio (`--profile lab`) es aparte y más grave:** Jupyter ahí ejecuta código
  arbitrario como root con el volumen de la DB montado. Se publica **sólo en `127.0.0.1`** por eso
  (ver `docker-compose.yml`, servicio `lab`); nunca en `0.0.0.0`.

## Precio Objetivo y Stop Loss

Cada ticker puede tener un precio objetivo (para tomar ganancias) y un stop loss (para cortar
pérdidas). Se cargan de **dos lados, y gana la app**:

1. **Desde la app**, en el detalle del ticker, tocando las tiles "Precio Objetivo" o "Stop Loss".
2. **Desde el Sheet**, en las 4 columnas opcionales de la pestaña `Instrumentos` (abajo).

### Desde la app (lo que fijás acá pisa al Sheet)

Los niveles fijados desde la app viven en `niveles_precio_override`, **una tabla aparte**, porque
el sync le hace DELETE + INSERT completo a `instrumentos_inversion` en cada corrida: un nivel
escrito ahí duraría hasta las 18:30 del mismo día. La precedencia se resuelve en un único lugar,
`services/niveles_analytics.py`, que es lo que consumen los dos lectores de niveles
(`get_rendimiento_por_ticker` y `get_ticker_position`); de ahí para abajo, alertas y diagnóstico
no saben de dónde salió el nivel.

El valor del Sheet se sigue leyendo y viaja en la API como referencia (`*_modo_sheet` /
`*_valor_sheet`, más `*_origen` con `"app" | "sheet" | "ninguno"`), así que la app puede mostrarlo
y ofrecer "volver al valor del Sheet". El override **no** se escribe de vuelta en el Sheet: si
después se edita esa celda, las dos fuentes dicen cosas distintas y manda la app.

Cambiar un nivel **re-arma** el aviso de Telegram de ese ticker
(`alertas_analytics.rearmar_por_cambio_de_nivel`): si no, la fila seguiría `disparada` y el nivel
nuevo quedaría silenciado por un cruce viejo. El aviso sale en la próxima corrida del job, no en
el momento de guardar.

### Desde el Sheet

Las 4 columnas son opcionales y deben coincidir exactamente en el Google Sheet y en
`sheet_local/sheet_inversiones.xlsx`:

| Columna | Valores | Significado |
|---|---|---|
| `Objetivo Modo` | `Porcentaje` o `Fijo` | cómo interpretar `Objetivo Valor` |
| `Objetivo Valor` | número | `Porcentaje`: % sobre el precio promedio de compra (ej. `20` = +20%). `Fijo`: precio absoluto |
| `Stop Loss Modo` | `Porcentaje` o `Fijo` | cómo interpretar `Stop Loss Valor` |
| `Stop Loss Valor` | número | `Porcentaje`: % de caída sobre el precio promedio de compra (ej. `-5`). `Fijo`: precio absoluto |

`Modo` y `Valor` deben completarse juntos (o dejarse ambos vacíos). Se ven en el detalle de
cada ticker en la app, junto con el % que falta para alcanzarlos — y quedan tapados si ese ticker
tiene un nivel fijado desde la app.

Además de verse en la app, **el cruce de estos niveles dispara un aviso por Telegram** (ver
"Avisos al celular" más abajo).

## Avisos al celular (Telegram)

El backend manda **un mensaje por Telegram** cuando una posición cruza su stop loss o su precio
objetivo, cuando un ticker de la watchlist entra en su zona de compra, y cuando dispara una señal
de una estrategia técnica habilitada. Llega con la app cerrada.

### Por qué Telegram y no notificaciones del navegador

La app se sirve por HTTP en la LAN (`http://smoa7001lx:8087`). Los navegadores no permiten la API
de notificaciones ni registran service workers en orígenes que no son seguros, así que Web Push
obligaría a montar HTTPS primero (con Tailscale Serve, por ejemplo). Telegram esquiva todo eso: es
un POST saliente del backend. De paso: **por el mismo motivo, el modo offline del service worker
sólo funciona entrando por `localhost`**, no desde el celular.

### Configuración

**Los pasos de puesta en marcha, uno por uno, están en
[`docs/alertas-telegram.md`](docs/alertas-telegram.md)** (crear el bot, sacar el chat id, sembrar el
estado inicial, qué hacer si falla). Acá queda sólo el resumen.

```
ALERTAS_ENABLED=true
TELEGRAM_BOT_TOKEN=...   # @BotFather → /newbot
TELEGRAM_CHAT_ID=...     # @userinfobot te responde tu "Id"
```

**En qué archivo** depende de cómo levantes la app, porque `--env-file` *reemplaza* al `.env` por
defecto en vez de sumarse:

| Cómo levantás | Archivo que compose lee |
|---|---|
| `docker compose -f docker-compose.yml -f docker-compose.corporate.yml up` | `.env` |
| `./docker-helper.sh corporate up` | `.env.corporate` |

Si usás las dos formas, las líneas tienen que estar en los dos archivos (ambos gitignored).
Para confirmar que llegaron al contenedor:

```bash
docker compose -f docker-compose.yml -f docker-compose.corporate.yml config | grep TELEGRAM
```

En Ajustes → "Avisos al celular" se ve el estado y hay un botón para mandar un mensaje de prueba;
en "Qué avisar" se eligen los tipos y las estrategias, y en "Últimos avisos" se ve el historial.

**Proxy corporativo**: el POST a `api.telegram.org` sale por `HTTP_PROXY`/`HTTPS_PROXY`
(`market_data/client.py` usa `trust_env=True`). Si el proxy bloquea Telegram, las alertas no van a
funcionar desde la máquina de desarrollo pero sí desde el servidor, que sale directo.

### Un aviso por cruce, no uno por corrida

Cada nivel vigilado guarda estado en la tabla `alertas_precio`: `armada` o `disparada`. Un cruce
avisa **una sola vez**; la alerta vuelve a `armada` sólo cuando el precio regresa al otro lado del
nivel y se aleja más de un 2% (`alertas_engine.BANDA_REARMADO_PCT`).

Esa banda de histéresis es lo que hace que la función sea usable: sin ella, un precio oscilando
alrededor del nivel generaría un aviso por corrida hasta que uno silencie el bot. La lógica está
en `services/alertas_engine.py` (puro, con tests) y el adaptador en `services/alertas_analytics.py`.

El estado **sobrevive al sync**: si se borrara, todos los niveles ya cruzados volverían a avisar.

Si el envío falla, la fila queda `disparada` con `entregada=0` y se reintenta en la corrida
siguiente, sin volver a tratar el cruce como nuevo.

### Señales de estrategia: mismo canal, otro antirrebote

Las señales técnicas (`estrategias_analytics.senales_recientes`) viajan por la misma tabla, con
`tipo = "estrategia:<id>"` y `cartera = ""`:

- **El id va dentro de `tipo`** y no en una columna propia porque tiene que entrar en el UNIQUE
  `(ticker, tipo, cartera)`, y SQLite no sabe alterar un UniqueConstraint sin reconstruir la tabla.
- **`cartera` queda vacía** porque una señal es sobre la serie del ticker, no sobre una tenencia:
  si la cartera entrara en la clave, un ticker con tenencia en dos carteras avisaría dos veces y
  mover la tenencia re-dispararía la señal. La cartera a mostrar viaja en el contexto.
- **No hay histéresis** (no hay nivel del cual alejarse): la deduplicación es por la **barra** de
  la señal, guardada en `detalle` (`senal_fecha`, `senal_tipo`). Eso resuelve de una vez el rebote
  —la misma señal aparece durante dos ruedas y sólo la primera avisa— y la secuencia
  compra → venta → compra del mismo par, donde cada señal cae en una barra distinta.

### Qué avisa y qué no: un interruptor por tipo de nivel y dos casillas por estrategia

- Los tipos de nivel se prenden en la tabla singleton `ajustes_avisos` (todos arrancan en 1 =
  el comportamiento previo). Hoy son cuatro: stop-loss, objetivo, zona de compra y zona de venta.
  Un tipo apagado **se sigue igual**: el cruce se guarda con `entregada=1` y `emitida_en=NULL`,
  así que prenderlo meses después no manda de golpe todo lo que pasó mientras estaba apagado.
- **Agregar un tipo a `alertas_engine.TIPOS` obliga a agregar su columna** en `ajustes_avisos` y su
  entrada en `avisos_config.CAMPO_POR_TIPO`: sin el interruptor, `tipos_habilitados` no lo incluye
  y sus cruces se guardarían silenciados para siempre, sin forma de prenderlos. Hay un `assert` en
  `avisos_config` que lo hace fallar al importar en vez de en producción.

### Zonas de precio: cada una se mide sobre su propia serie

- Una `ZonaPrecio` lleva `variante` (`local` | `subyacente`) y se compara **siempre** contra el
  precio de esa serie: el cotizado acá, o el del instrumento en EE.UU. en USD nativo. **Nunca se
  convierte de moneda** — son dos instrumentos, no el mismo precio en dos monedas (mismo criterio
  que `ohlcv_analytics`). Una zona cuya serie no tiene precio no genera candidata.
- El precio del subyacente sale de `precios_subyacente` (lo refresca el job liviano desde yfinance,
  sin cupo de IOL), con el último cierre de `TICKER@SUB` como respaldo. **No** se escribe en
  `serie_ohlcv`: esa serie alimenta indicadores y backtests, y `debe_reemplazar_barra` no dejaría
  que un close-only intradía pise la vela del día en curso.
- `cruzado` es "el precio cruzó el **borde de disparo**" (el techo en una zona de compra, el piso
  en una de venta), no "está dentro del rango": en una zona de compra de 1150-1250, un precio de
  900 está *más* adentro de la oportunidad. Consecuencia directa: el borde opuesto **no** puede
  re-armar la alerta (si a 900 sigue cruzada, salir por abajo no es un evento), así que el
  antirrebote sigue siendo la banda porcentual sobre el borde de disparo.
- La `cartera` de una alerta de zona es siempre `""`: la zona es una decisión sobre el
  **instrumento**. Si la cartera entrara en la clave, el mismo ticker con tenencia en dos carteras
  avisaría dos veces de la misma zona.
- Cada estrategia tiene `notificar_compra` y `notificar_venta` por separado: confiar en las
  entradas de una estrategia no obliga a confiar en sus salidas. **Arrancan en 0**: el catálogo
  siembra 16 presets reusables sobre todo el universo, y prenderlos todos serían decenas de
  mensajes diarios. Si no hay ninguna prendida, `senales_recientes` **no se llama** — correr hasta
  400 backtests para descartarlos es el gasto más caro del job.
- `guardar_por_nombre` (el upsert que usa el editor) **no toca** esas casillas: re-guardar una
  definición no puede silenciar una estrategia.
- Todo se maneja desde Ajustes → "Qué avisar" (`services/avisos_config.py`).

### El texto del aviso

El formato vive en `alertas_engine` porque es parte de la decisión de "cuándo avisar": un aviso
que no se entiende de un vistazo en el celular es un aviso que no sirve. Cada aviso dice la acción
(`COMPRA`/`VENTA`/`REVISAR`), el origen (cartera X o watchlist, y si ya hay posición), la regla que
lo disparó y la tenencia.

Tres cosas a tener en cuenta si se toca:

- **Va en `parse_mode=HTML`**, así que *todo dato* se escapa con `escapar_html` (`&` primero). Un
  `&` crudo —`S&P 500`, `AT&T`— hace que Telegram rechace el mensaje **entero** con 400, no que se
  vea raro un nombre. `telegram.enviar` reintenta una vez sin `parse_mode` si el 400 es de formato:
  un bug de escapado tiene que degradar el aviso, no hacerlo desaparecer.
- **El recorte es por avisos enteros** (`texto_notificacion`, presupuesto 3800 de los 4096 de
  Telegram): completo → compacto → compacto con tope por bloque → sólo conteos. Cortar a mitad de
  un tag no pierde un pedazo del mensaje, pierde todo.
- **Todo el contexto se persiste en `detalle`** (`contexto_a_detalle` / `detalle_a_contexto`),
  porque el reintento reconstruye el aviso sólo desde las columnas más ese JSON. Lo que no viaje
  ahí hace que el reintento mande un texto distinto al original. `detalle` es una columna JSON:
  `senal_fecha` va en ISO, nunca como `date`.

### Endpoints

| Método | Ruta | Para qué |
|---|---|---|
| GET | `/api/inversiones/alertas` | historial de cruces avisados |
| GET | `/api/inversiones/alertas/estado` | si están habilitadas/configuradas y el último aviso |
| POST | `/api/inversiones/alertas/probar` | mensaje de prueba, para verificar la configuración |
| POST | `/api/inversiones/alertas/evaluar` | evaluar ahora (`?notificar=false` siembra el estado sin avisar) |
| GET | `/api/inversiones/alertas/config` | los interruptores por tipo + las casillas de cada estrategia |
| PUT | `/api/inversiones/alertas/config` | prender/apagar tipos de nivel (parcial: `null` no toca) |
| PUT | `/api/inversiones/alertas/config/estrategias/{id}` | prender/apagar compras y ventas de una estrategia |

**La primera vez conviene correr `POST /alertas/evaluar?notificar=false`**: deja todos los avisos
ya disparados como "ya vistos" sin mandar nada, y así el primer aviso real es un cruce nuevo y no
una andanada con todo el historial. Hasta 2026-10 esa receta **no funcionaba**: las filas quedaban
`entregada=0` y la corrida siguiente las levantaba como pendientes de entrega y mandaba la andanada
igual.

## Jobs programados: datos y alertas sin abrir la app

El sync siempre fue **pull desde el cliente** (el botón del header o `useAutoSync` al abrir la
PWA). Es decir: si nadie abre la app, no entra ningún dato — y una alerta que sólo se evalúa
cuando uno mira la app no sirve para nada.

`services/scheduler.py` programa **dos jobs** (APScheduler, dentro del contenedor), ambos de lunes
a viernes:

| Job | Cuándo | Qué hace |
|---|---|---|
| `sync_y_alertas` | 18:30 (tras el cierre) | `sync_from_sheet` completo + evaluar alertas |
| `refresco_y_alertas` | 11, 13, 15, 17 (la rueda) | sólo cotizaciones + evaluar alertas |

```
SCHEDULER_ENABLED=true          # apagado por default: prenderlo sólo en el servidor
SCHEDULER_HORA=18               # sync completo
SCHEDULER_MINUTO=30
SCHEDULER_TZ=America/Argentina/Buenos_Aires
REFRESCO_HORAS=11,13,15,17      # refresco liviano; vacío lo desactiva
REFRESCO_MINUTO=5
```

### Por qué son dos y no uno más frecuente

Un `sync_from_sheet` lee el Google Sheet entero, valida ocho pestañas, hace ~20 bloques de
delete/insert y escribe un `SyncRun`. Correrlo cada dos horas tendría dos problemas que **no son el
cupo de IOL**:

- el historial de `SyncRun` se conserva de a 20 (`_prune_sync_runs`), así que con varias corridas
  por día el sparkline de Calidad de datos cubriría horas en vez de semanas;
- su `health_score` sería perfecto por construcción (no mira el Sheet), inflando la métrica que
  sirve justamente para detectar problemas del Sheet.

De ahí el job liviano, `services/refresco_precios.py`: pide el precio del día por la **misma vía que
el sync** (`market_data.precios.fetch_precios_api`, así que la precedencia `iol > sheet > api`, la
calibración de escala y el conteo de cupo son los mismos, no una copia), hace upsert en
`precios_instrumento` + espejo close-only en `serie_ohlcv`, re-cotiza la watchlist y deja la marca
en la tabla `refresco_precios` (una fila). **No** lee el Sheet, no hace backfill histórico, no toca
CER/MEP y no escribe en el historial de calidad de datos.

### Consecuencia en la UI

El chip de frescura del encabezado sigue mostrando el último **sync completo**, que es lo correcto:
los movimientos y los niveles de stop-loss vienen del Sheet. La frescura de las **cotizaciones** se
ve en Ajustes → "Cotizaciones", y sale de `GET /api/inversiones/refrescar-precios/estado`.

### Resto de las garantías

- **Apagado en la máquina de desarrollo**: cada corrida gasta cupo de IOL.
- Los dos jobs respetan el mutex de sync (`services/sync_lock.py`, compartido con `POST /sync`): si
  hay una corrida en curso, la otra se saltea en vez de encolarse. El refresco también escribe en
  `precios_instrumento`, así que dos escritores simultáneos sobre SQLite es justo lo que el lock
  evita.
- Las alertas se evalúan **aunque la traída de datos falle o se saltee**: los niveles se comparan
  contra los últimos precios que haya en la base, y un sync fallido no es razón para no avisar de un
  cruce que ya pasó.
- Costo de cupo: tanto un sync como un refresco gastan ~10 llamadas (1 token + ~9 paneles). Un sync
  diario + 4 refrescos por día hábil son ~1.050 al mes contra el tope de 22.000: **menos del 5%**.

### Dispararlo a mano

```bash
curl -X POST http://localhost:8087/api/inversiones/refrescar-precios
```

Mismo trabajo que el job de la rueda, para verificarlo sin esperar al horario.

## Clasificación de instrumentos y valuación contra pares

**Qué resuelve.** Sector y país eran texto libre del Sheet (KO con `País=AR`, "Cosumo Masivo") y no
había ningún dato fundamental. Ahora cada emisor del catálogo de IOL tiene clasificación y
fundamentales de Yahoo (`get_info()`), y las pantallas agrupan por un único vocabulario.

**Piezas**, en orden de dependencia:

| Módulo | Qué hace |
|---|---|
| `services/clasificacion_engine.py` | Puro. Vocabulario (sectores, regiones MSCI, tipos), traducción desde Yahoo/Sheet, variantes de moneda (`AAPL`/`AAPLC`/`AAPLD` → un emisor), símbolo en Yahoo, `resolver()` campo a campo |
| `catalogos/clasificacion_seed.json` | Excepciones versionadas: variantes raras, símbolos Yahoo distintos (`BRKB`, `.SA`, locales con ADR → ADR) y exposición país (VIST → Argentina) |
| `services/fundamentales_ingesta.py` | Job: cola por prioridad, topes, backoff, corte por límite de tasa, conversión a USD, un solo commit |
| `services/clasificacion_analytics.py` | Resolutor único (`clasificaciones(db)`) que leen todas las pantallas; correcciones manuales |
| `services/pares_engine.py` | Puro. Elige comparables |
| `services/valuacion_engine.py` | Puro. Limpia métricas, percentiles, lecturas con regla visible |
| `services/valuacion_analytics.py` | Adaptador DB de las dos anteriores |
| `services/comparador_engine.py` | Puro. Comparador "¿qué compraría en su lugar?": comparabilidad, tabla por sector, ranking y conclusión (reglas v1) |
| `services/comparador_analytics.py` | Adaptador DB del comparador (reutiliza `Universo`) |
| `services/valor_razonable_engine.py` | Puro. Valor razonable y escenarios por múltiplos de pares, margen de seguridad vs. potencial, supuestos editables (reglas v1) |
| `services/valor_razonable_analytics.py` | Adaptador DB del valor razonable (reutiliza `Universo`; lee/guarda `valor_supuestos`) |
| `services/impacto_cartera_engine.py` | Puro. Impacto de sumar un monto a la cartera: pesos antes/después por eje, observaciones con los umbrales de Salud (reglas v1) |
| `services/impacto_cartera_analytics.py` | Adaptador: `_clasificados_valorizados` + una tenencia simulada en memoria; agrupa con `_agrupar` (la de Exposición) |
| `services/historial_diagnosticos.py` | Foto point-in-time del diagnóstico (+ comparador y valor razonable de lo que está en cartera/watchlist) tras cada ingesta; línea de tiempo y backtest |
| `services/historial_engine.py` | Puro. Retornos posteriores por estado del diagnóstico (entradas a un estado, muestra mínima, línea de base) |
| `services/alertas_diagnostico_engine.py` | Puro. Cuándo avisar de un cambio de estado del diagnóstico (siembra, pendiente, confirmación, silencios) |
| `routers/clasificacion.py` | Endpoints |

Tablas nuevas (`create_all`, sin migración): `clasificacion_auto`, `fundamentales_snapshot` (se
retienen 8 por símbolo), `clasificacion_override`, `pares_override`, `ingesta_fundamentales`, `valor_supuestos`, `diagnostico_historial`, `diagnostico_alerta_estado`
(más la columna `ajustes_avisos.avisar_diagnostico`, con `ALTER` idempotente en `init_db`).
Ninguna tiene FK a `instrumentos_inversion`: el sync la vacía.

**Precedencia** (`clasificacion_engine.resolver`): corrección manual > seed > Yahoo > Sheet, con
tres excepciones: "Liquidez" en el sector del Sheet es un rol y gana sobre Yahoo; renta fija y FCI
usan el Sheet (Yahoo no los cubre); el país "Argentina" del Sheet en un CEDEAR se ignora (es la
plaza, no el emisor).

**Interruptor de reversión**: `CLASIFICACION_AUTO=false` devuelve exactamente el texto del Sheet en
todas las pantallas (sin eje Región, Descomposición por País). Antes de prenderlo en una base real:

```bash
docker compose exec backend python -m scripts.verificar_clasificacion
```

lista qué tickers cambian de tipo/sector/país y de qué fuente sale, y confirma que el total de cada
eje no cambia (la clasificación mueve etiquetas, nunca plata). Lo mismo en
`GET /api/inversiones/clasificacion/diferencias`.

### Ingesta (job `fundamentales`)

```
FUNDAMENTALES_HORAS=3,19          # lun-sáb; vacío lo desactiva (requiere SCHEDULER_ENABLED)
FUNDAMENTALES_MINUTO=30
FUNDAMENTALES_MAX_POR_CORRIDA=60  # emisores por corrida (~2 llamadas a Yahoo c/u)
FUNDAMENTALES_PAUSA_SEG=0.5
HISTORIAL_UNIVERSO=cartera,watchlist  # qué emisores guarda el historial de diagnósticos (+ catalogo); 0 llamadas a Yahoo
```

- ~460 emisores de renta variable: con dos corridas por día el catálogo se completa en ~4 días.
  Prioridad: cartera y watchlist sin datos → pares de lo propio con datos vencidos → lo propio
  vencido (>7 días) → resto nunca visto → resto vencido (>14 días).
- **No toca IOL** ni corre dentro del sync. La red va sin lock; la escritura es un commit con
  `sync_lock` (timeout 300 s).
- Ante un 429/`YFRateLimitError` o 5 errores seguidos corta la corrida y guarda lo obtenido.
  Backoff por emisor `2^n` días (tope 30); `no_encontrado` se reintenta a los 90 días.
- Magnitudes a USD: ARS por el MEP de la base, el resto por el par de Yahoo (`EURUSD=X`). Si el
  balance está en otra moneda que la cotización (ADRs argentinos, `.BA`), P/E y P/Ventas se
  recalculan en USD y los ratios que no se pueden recalcular se descartan.
- Unidades de Yahoo (verificadas): `dividendYield` y `netExpenseRatio` en %, `yield` en fracción,
  `debtToEquity` en %.

Dispararlo a mano:

```bash
curl -X POST http://localhost:8087/api/inversiones/clasificacion/actualizar-lote     # corrida normal, en segundo plano
curl -X POST http://localhost:8087/api/inversiones/clasificacion/actualizar \
     -H 'Content-Type: application/json' -d '{"tickers": ["KO", "GGAL"]}'          # hasta 5, sincrónico
curl http://localhost:8087/api/inversiones/clasificacion/estado                      # cobertura
```

Recargar todo el catálogo ignorando frescura (p.ej. después de cambiar qué se guarda, como la
serie semanal de 5 años del gráfico de precio vs. pares). Son ~900 llamadas, 15-20 minutos; si
Yahoo limita, se corta sola y guarda lo obtenido, y se vuelve a correr:

```bash
docker compose exec backend python -c "from app.database import SessionLocal; from app.services import fundamentales_ingesta as fi; print(fi.correr(SessionLocal(), max_emisores=500, forzar=True))"
```

El alta en watchlist pide los datos del ticker nuevo en segundo plano.

### Endpoints

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/valuacion?universo=cartera\|watchlist\|catalogo` | Lectura por emisor (filtros `tipo`, `sector`, `region`, `lectura`) |
| GET | `/valuacion/{ticker}` | Ficha: clasificación con fuentes, pares y criterio, tabla, percentiles, frases, fuerza relativa |
| GET | `/valuacion/{ticker}/comparador?con=A,B` | Comparador de alternativas (ver más abajo). `con` = hasta 6 tickers separados por coma; sin `con`, usa el grupo de pares |
| GET | `/valuacion/{ticker}/valor-razonable?con=A,B` | Valor razonable y escenarios (ver más abajo). `con` = emisores de referencia efímeros, hasta 6; sin `con`, su grupo de pares |
| PUT/DELETE | `/valuacion/{ticker}/valor-razonable/supuestos` | Guardar (`{ajuste_pct, excluir[], multiplos{}}`) o restablecer los supuestos; devuelven el cálculo recalculado |
| POST | `/carteras/{nombre}/impacto-compra`, `/consolidado/impacto-compra` | Simulador de impacto en cartera (ver más abajo). Body `{ticker, monto_usd}`; 404 si el ticker no existe, 422 si es inválido. No persiste nada |
| GET | `/valuacion/{ticker}/historial` | Línea de tiempo del diagnóstico (fotos guardadas, qué cambió entre una y otra, marca de cambio de reglas) |
| GET | `/valuacion/historial/backtest` | Retornos posteriores por estado, sólo con lo acumulado; "muestra insuficiente" hasta 30 eventos por celda |
| GET/PUT | `/clasificacion/{ticker}` | Ver / corregir tipo, sector, industria, país, región, símbolo Yahoo |
| DELETE | `/clasificacion/{ticker}/{campo}` | Volver al automático |
| POST | `/pares/{ticker}` | `{par, accion: agregar\|quitar}` |
| DELETE | `/pares/{ticker}/{par}` | Deshacer la corrección de un par |

### Diagnóstico integral (reglas v2)

`diagnostico_empresa_engine.py` (puro, sin DB ni red) separa lo que antes era una sola lectura en
**cinco preguntas independientes**, cada una con estado en palabras, razones, regla visible y
"qué falta". **No hay puntaje único.** `VERSION_REGLAS = 2` viaja en la respuesta (`diagnostico.version_reglas`);
si cambia una regla o un umbral hay que subirla (prepara el historial de diagnósticos).

| Dimensión | Estados | Cómo se decide (resumen; el texto exacto está en `regla` de la respuesta) |
|---|---|---|
| Valuación | la lectura de siempre | 2+ **familias** en el cuarto más barato/caro del grupo (ver abajo) |
| Calidad | Alta / Media / Débil / Sin conclusión | familias márgenes y retornos; margen operativo/neto o ROE negativo = Débil aunque los pares estén peor |
| Crecimiento | Alto / Medio / Bajo / En caída / Sin conclusión | ingresos y ganancias interanuales (observado); crecimiento esperado = P/E ÷ P/E estimado − 1 (estimación, suma pero no decide solo); ingresos < −2 % = En caída |
| Solidez financiera | Sólida / Con señales de atención / Frágil | fuertes: Deuda/Patrimonio > 2, FCF negativo, sin ganancias, payout > 100 %; moderadas: liquidez corriente < 1, beta > 1,5, deuda en el cuarto peor |
| Confianza de los datos | Alta / Media / Baja | el peor de: cobertura (≥ 70 % / ≥ 40 %), pares con datos (≥ 4 / ≥ 2), frescura (≤ 21 / ≤ 60 días), antigüedad del balance (≤ 150 / ≤ 270 días), balances de períodos distintos, conversión de moneda |

Principios (están en los tests): **faltante ≠ negativo** (un dato que Yahoo no trae se lista en
"qué falta", nunca baja un estado), **no aplica ≠ faltante** (un banco no tiene EV/EBITDA ni margen
bruto; un ETF sólo se evalúa por valuación y confianza), y cada razón lleva su `origen`:
`observado` (lo informó Yahoo), `estimado` (proviene de estimaciones de analistas: P/E estimado, PEG,
crecimiento esperado) o `calculado` (lo derivó la app). Las conclusiones las calcula siempre la app.

**Familias de valuación** (`valuacion_engine.FAMILIAS`): ganancias (P/E, P/E estimado, PEG), ventas y
EBITDA, flujo de caja, valor libro, dividendo (y costos en ETFs). Cada familia vota lo que vota la
mayoría de sus métricas con banda (empate = media): P/E, P/E estimado y PEG juntos valen **un** voto.
El dividendo siempre, y el valor libro en Tecnología/Comunicaciones/Salud (`SECTORES_PATRIMONIO_NO_DECIDE`),
"suman pero no deciden": no alcanzan solos y un valor "peor" ahí no se cuenta como "cara". Esto
**cambió lecturas** respecto de la v1 (que contaba cada métrica); el motor sigue declarando en
`regla_lectura` lo que usó de verdad.

Otros cambios en este paso:
- El método (percentil vs. comparación directa contra un único par) se decide **por métrica**: antes una
  sola métrica con un par bastaba para que toda la regla y la advertencia hablaran de "15 % contra el par".
- `Universo` toma la serie semanal del snapshot más nuevo **que la tenga**; si el último quedó sin serie
  (falla o 429) ya no se pierde el momentum, y se avisa si la serie es más vieja que los fundamentales.
- La corrección manual de industria (en castellano) ahora encuentra pares (se compara con `industria_legible`).
- El flujo de caja libre de un banco (sector Financiero) no se usa.
- Datos nuevos de Yahoo, **misma llamada `get_info()`, sin consultas extra**: `mostRecentQuarter` (período del
  balance), `payoutRatio`, `currentRatio`. Entran al JSON `metricas` (sin migración de esquema) y aparecen en
  la próxima ingesta; mientras tanto el motor los trata como ausentes, no como negativos.
- La ficha del ticker ya no da "Ticker no encontrado" para lo que no está en el Sheet (catálogo, watchlist,
  pares): muestra la pestaña Pares con un aviso.

API (aditiva): `GET /valuacion/{ticker}` suma `diagnostico` y `origen` en cada fila de la tabla;
`GET /valuacion` suma `dimensiones` (estado, nivel, percentil) por ítem. La lista se filtra y ordena en el
cliente (`ValuacionPares.tsx`), un criterio explícito a la vez.

### Comparador "¿qué compraría en su lugar?" (reglas v1)

`comparador_engine.py` (puro) + `comparador_analytics.py` (adaptador; arma un `Universo` por request y se
cachea con `cache_por_sync`: `con` es parte de la clave, y cualquier escritura —`ParOverride`,
`ClasificacionOverride`— o sync lo invalida). Sin tablas ni columnas nuevas; la elección de alternativas
es efímera (parámetro `con`), el grupo persistente sigue siendo `ParOverride`.

- **Comparabilidad** (`evaluar` por criterios: emisor, tipo, modelo de negocio, industria/categoría,
  tamaño, región, cobertura, período contable, moneda, frescura). *No comparable* (descarte duro, va a
  `rechazadas` con el motivo): mismo emisor (mismo `ticker_base` o `simbolo_yahoo`: CEDEAR vs. subyacente,
  ADR vs. local), ETF vs. empresa, modelo distinto (financiero / inmobiliario / operativo), sin fundamentales
  o cobertura < 40 %. *Alta* = misma industria + tamaño 0,2-5× + misma región; *media* = misma industria con
  una de las otras dos, o mismo sector con tamaño y región; *baja* = el resto (se ve, no cuenta). Datos de
  otro período/moneda/frescura topean "alta" en "media"; un par agregado a mano sube "baja" a "media".
- **Selección**: sin `con`, los pares del grupo con nivel alta/media (tope `N_DEFAULT = 4`); con `con`, esos
  (tope `MAX_ALTERNATIVAS = 6`; dos tickers del mismo emisor cuentan una vez). `sugeridas` = candidatos
  alta/media fuera de la selección (los `quitado` a mano no se sugieren). `MIN_ALTERNATIVAS = 2`: con menos,
  estado `insuficiente` (tabla sí; ranking y conclusión no) y mensaje con lo que falta.
- **Tabla**: métricas por modelo (`METRICAS_POR_MODELO`), unidad, período (`PERIODO_METRICA`), origen,
  estado de celda (`dato | sin_dato | no_aplica | sin_ganancias | moneda`), mejor/peor por fila entre los
  miembros que cuentan, y las que no aplican con su motivo.
- **Ranking**: se corre `ve.evaluar` + `diagnostico_empresa_engine.diagnosticar` de cada miembro **contra
  los demás miembros** (los percentiles de los diagnósticos individuales vienen de grupos distintos y no se
  pueden ordenar entre sí). Posición por dimensión; tercio (arriba < 1/3, abajo > 2/3 de los puestos).
- **Conclusión**: R1 (más cara + fundamento fuerte, sin debilidad), R2 (más cara sin respaldo), R3 (más
  barata + debilidad), R4 (más barata sin debilidades), R5 (en el medio), R0 (sin datos de valuación), ETF
  (costo/valuación). Fundamento fuerte = tercio mejor sin alerta propia; debilidad = tercio peor o alerta
  propia (calidad débil, ingresos en caída, solidez frágil). Aparte, dominancia por par (±15 %). "Por qué
  podría merecer un múltiplo mayor/menor" sale de las razones de cada dimensión (con origen). Firmeza
  alta/media/baja según miembros, confianza de datos y períodos/monedas. Un test garantiza que ningún texto
  dice comprá/vendé/recomendar.

### Valor razonable y escenarios (reglas v1)

`valor_razonable_engine.py` (puro) + `valor_razonable_analytics.py` (adaptador con `cache_por_sync`; los
supuestos viven en `valor_supuestos`, una fila por `ticker_base` con un JSON validado por
`normalizar_supuestos`; cualquier escritura invalida el caché). **0 llamadas nuevas a Yahoo**: sale de la
foto TTM que ya existe.

- **Cálculo, todo en proporciones** (no depende de la moneda del balance): múltiplo de precio →
  `valor = precio × M_ref ÷ M_propio`; EV/EBITDA → `cap_ref = M_ref × EV ÷ M_propio − (EV − cap)` y
  `valor = precio × cap_ref ÷ cap` (deuda neta ≈ EV − capitalización, con minoritarios/preferidas dentro).
  Precio/FCF = 1 ÷ rendimiento del FCF. Escenarios: pesimista = cuartil 1, base = mediana, optimista =
  cuartil 3 de los múltiplos de los pares (winsorizados con la regla de `valuacion_engine`).
- **Familias** (`valuacion_engine.FAMILIAS`): mediana dentro de la familia y luego entre familias; las que
  "sólo apoyan" (`familias_que_solo_apoyan`) se muestran y no deciden. Métodos pertinentes por modelo de
  negocio: `comparador_engine.METRICAS_POR_MODELO` (banco: P/E, P/E est., P/VL; inmobiliaria: P/VL, P/FCF).
  ETF → `no_aplica`.
- **Mínimos**: `N_MIN_PARES = 4` por método y `FAMILIAS_MINIMAS = 2`; si no, `sin_conclusion` con lo que falta.
  Método sin dato propio = `falta`; sin ganancias / banco sin EV / balance en otra moneda = `no_aplica`
  (no es faltante); factor fuera de 0,2×–5× o patrimonio ≤ 0 = `inestable` (se muestra, no entra).
- **Margen de seguridad ≠ potencial**: `(V − P) ÷ V` y `(V − P) ÷ P` (V=125, P=100 → 20 % y +25 %).
- **Confianza** por puntos (≥3 familias, dispersión ≤ 1,5×, ≥6 pares por método), limitada por la
  confianza de datos del diagnóstico; dispersión > 2× = "no convergen" y confianza baja.
- **Supuestos editables**: ajuste general (±50 %), métodos excluidos y múltiplo fijo por método (el ajuste
  no toca un múltiplo fijado a mano). Se repiten en la respuesta.
- **Referencia de analistas** (`targetMeanPrice`, `targetLow/HighPrice`, `numberOfAnalystOpinions`, claves
  nuevas de `yahoo.CLAVES_NUMERO`, mismo `get_info()`): se muestra aparte y sólo con `ratios_precio_confiables`;
  **no entra** al cálculo. Aparece tras la próxima ingesta.
- Un test garantiza que ningún texto dice comprá/vendé/recomendar.

**Qué no se hizo (propuesto):** múltiplos históricos propios y consistencia de resultados (3b: tabla de
estados contables anuales para cartera + watchlist en un job aparte, ~3 llamadas extra por emisor; hoy sólo
hay una foto TTM y hasta 8 snapshots), alertas por cambio de diagnóstico e historial (`version_reglas` de
diagnóstico, comparador y valor razonable ya viajan en la respuesta). Sin historia contable de varios
años la **consistencia** de resultados no se evalúa, y la pantalla lo dice.

### Impacto en cartera: "¿cómo cambiaría mi cartera?" (reglas v1)

`impacto_cartera_engine.py` (puro) + `impacto_cartera_analytics.py`. **No persiste nada** (un test cuenta las
filas de todas las tablas antes y después), no escribe movimientos, no estima precio ni cantidad. Sin caché
(parámetros libres, igual que `rebalanceo/simular`).

- "Antes" = `_clasificados_valorizados` (criterio único de totales: sin cotización → al costo + aviso,
  buckets residuales `SIN_*`). "Después" = `dataclasses.replace(pos, valores=… + [(cartera, ticker, N, N·MEP)])`
  con la clasificación del ticker (la de la posición si ya la tiene; si no, `Contexto.resolver` con la
  ficha de la watchlist). Sin MEP la compra entra con 0 ARS y se avisa, como cualquier posición sin valor ARS.
- Cada eje se agrupa con `_agrupar` —la de Exposición—, así que "antes" coincide con esa pantalla (hay un test
  de equivalencia contra `get_exposicion`). **No se refactorizó `get_exposicion`.**
- **Eje Emisor (nuevo)**: agrupa por `Contexto.base`, o sea CEDEAR en pesos + CEDEAR en dólares + acción de
  origen = un emisor. Exposición y Contribución **no** hacen esto (su eje "Ticker" es el ticker local).
  Otros ejes: Sector, País, Región (sólo en modo auto), Tipo de instrumento.
- **Observaciones** con los umbrales de `salud_engine` citados en `regla`: peso del emisor (atención ≥ 20 %,
  revisar ≥ 30 %, o `peso_maximo` configurado y 1,5× para revisar; el umbral es "desde"), país (70 % / 90 %,
  sólo si el peso sube y no es un bucket residual), diversificación (emisores equivalentes < 5 / < 3, avisa
  al cruzar para peor y como dato al mejorar), monto que cae en un bucket residual, y emisor que ya estaba
  en cartera. Un test garantiza que ningún texto dice comprá/vendé/recomendar (los textos dicen "pasaría",
  "quedaría").
- Frontend: tarjeta `ImpactoCartera.tsx` en la pestaña Pares; los importes van por `useFormatoFijo('USD')`
  (modo privacidad) y los pesos quedan visibles, como en Exposición.

**Qué no se hizo (propuesto):** efecto sobre riesgo/rendimiento esperado, cantidad de títulos (requiere
precio), simular ventas o varios tickers a la vez, y el eje "Ticker" de Exposición sigue sin unificar
variantes.

### Historial de diagnósticos y alertas por cambio de estado (reglas v1)

**Historial** (`historial_diagnosticos.py`, tabla `diagnostico_historial`). Después de cada corrida del job
`fundamentales` (`scheduler._registrar_historial_diagnosticos`, con su propia sesión y su propio `try/except`:
un fallo no toca la ingesta ni al revés; **fuera** del commit único de la ingesta y de `sync_lock`) se arma el
`Universo` **una sola vez** y se guarda una foto por emisor del universo `HISTORIAL_UNIVERSO` (default
`cartera,watchlist`; `catalogo` suma todo). Para lo que está en cartera o watchlist la foto incluye además un
extracto del comparador (estado, ranking, regla de la conclusión; nunca `tabla`/`pares`/`rechazadas`) y del
valor razonable; para `get_comparador`/`get_valor_razonable` se separó el cuerpo en `calcular(u, …)`.

- **Point-in-time**: la foto lleva `version_diagnostico/comparador/valor`, estados por dimensión con su razón
  y su regla, métricas, pares, precio y `fecha_dato`; nunca se recalcula ni se edita. Fechas en ISO.
- **Sólo si cambió algo** (`huella` = versiones + `fecha_dato` + estados/niveles + lectura + pares; los
  percentiles, el precio y las métricas no entran) → la tabla crece con los cambios, no con los días. Sin
  purga: medir el crecimiento real en el servidor. Emisores sin fundamentales no generan foto; renta fija y
  FCI se saltean.
- **Backtest** (`historial_engine`): una *entrada a un estado* (primera foto o cambio, misma versión de
  reglas) es un evento; retorno del precio en USD a 30/90/180 días (último cierre ≤ fecha de la foto →
  primer cierre ≥ fecha + horizonte, tolerancia 10 días, sin rellenar); celdas por `(dimensión, estado,
  versión)`; **menos de 30 eventos = sin promedio**; siempre junto a la línea de base de todos los eventos.
  Hoy responde "muestra insuficiente".

**Alertas** (`alertas_diagnostico_engine`, tipo `diagnostico:<dimensión>` en `alertas_precio`, `cartera=""`).
Dimensiones que avisan: valuación, calidad, solidez. Es la tercera familia de alerta, con su propio
antirrebote (por transición, sin nivel):
1. se silencia —sin tocar el estado— si el estado no aplica o no tiene datos, el snapshot tiene más de 21
   días (`MAX_DIAS_DATO`, inclusivo) o la confianza global es baja (**este silencio por dato viejo no existía
   en el motor de alertas**);
2. primera vez → **siembra** el estado, sin avisar; 3. cambio de `version_reglas` → **re-siembra** sin
   avisar (un cambio de reglas no es un cambio de la empresa); 4. mismo estado → cancela el pendiente;
5. estado distinto → **pendiente**, y recién se avisa cuando el *mismo* estado se ve en un snapshot con otra
   `fecha_dato` (la misma lectura no confirma; oscilar en el borde de una banda no avisa nunca).
El estado vive en `diagnostico_alerta_estado` (aparte de `alertas_precio`, porque tiene que avanzar también con
el aviso silenciado); el aviso emitido va a `alertas_precio` y hereda entrega, reintento e historial. Lee la
**última foto del historial**, no recalcula nada: sin historial, no hay alertas. Interruptor
`avisar_diagnostico` (default prendido; apagado se sigue el estado y sólo se silencia). Mensaje: bloque
"CAMBIO DE DIAGNÓSTICO" con ticker, origen, `dimensión: de → a`, razón, fecha del dato, versión de reglas y
"información de seguimiento, no una indicación de operar". Tests garantizan que ningún texto (ni las razones
guardadas) dice comprá/vendé/recomendar.

**Qué no se hizo (propuesto):** purga/compactación del historial (hay que medir el crecimiento), registro del
catálogo completo (medir el costo en el servidor antes de subir `HISTORIAL_UNIVERSO`), alertas de
crecimiento/confianza, avisos por cambio de comparador o de valor razonable, y un backtest con benchmark de
mercado (hoy sólo la línea de base de los propios eventos).

### Limitaciones conocidas

- Bonos, ONs, letras y FCI no se comparan todavía (etapa 2: curva TIR vs. duration por moneda/ley).
- Yahoo trae ratios raros en algunos ADR (P/Valor libro de DEO, por ejemplo): se recortan outliers
  con 5+ pares y la tabla lado a lado los deja a la vista, pero no se corrigen.
- Para bancos ADR (balance en ARS) quedan pocos múltiplos comparables: el P/Valor libro no se
  recalcula en USD.

## Logs

`LOG_LEVEL` (default `INFO`) fija el nivel del root logger. **Antes no había configuración de
logging**, así que el root quedaba en `WARNING` de Python y ningún `logger.info` de la app se
emitía nunca — incluido el resumen de cada sync. Con un job que corre solo a las 18:30, eso era
inoperable.

`docker-compose.yml` limita el `json-file` del backend a 5 archivos de 10 MB: con INFO los logs
crecen de verdad y sin rotación llenarían el disco del host.

```bash
docker compose logs -f backend
```

## Watchlist

Sirve para seguir instrumentos que **todavía no están en cartera** (no tienen movimientos) y que la
app avise cuando el precio se acerca a un precio de compra.

**No sale del Sheet.** Se gestiona desde la propia pantalla ("Más" → "Watchlist"): se toca
"Agregar", se busca el instrumento en el catálogo de IOL —con filtro por familia: acción, CEDEAR,
bono, ON, letra o FCI—, la app le baja el último precio en el acto y se le fija el precio objetivo
de compra. Tocando una fila se edita el objetivo, se anota una nota, se refresca el precio o se deja
de seguir. Si existía una pestaña `Watchlist` en el Sheet, se ignora.

### El catálogo de instrumentos

El universo de tickers elegibles sale de `catalogos/iol_catalogo.json` (2.289 símbolos, versionado
en el repo, montado read-only en `/app/catalogos`). Lo genera
`docker compose exec backend python -m scripts.iol_catalogo` (~42 llamadas a IOL, ver su docstring),
que escribe en `/app/data/iol_catalogo.json`; `services/catalogo_instrumentos.py` prefiere esa copia
si existe, así que regenerarlo actualiza la app sin rebuildear. La ruta se puede forzar con
`IOL_CATALOGO_FILE`.

El catálogo no trae un campo de tipo: el tipo se deriva del prefijo de `paneles`
(`Acciones/CEDEARs` → `CEDEAR`, `ObligacionesNegociables/Todas` → `ON`, ...), con los strings que
los clasificadores de `market_data/precios.py` ya reconocen. La `moneda` que declara **no es
confiable** (hay ONs en dólares listadas como `AR$`): es sólo un default de display, y la moneda
real la manda la fuente al cotizar.

### Precios, sin calibración de escala

`fetch_precios_watchlist_catalogo` toma la cotización de IOL **tal cual**, con factor 1.0: el
símbolo viene del catálogo de IOL, así que ya está en la unidad correcta y no hay ninguna serie del
Sheet contra la cual reconciliarlo. Tres intentos, del más barato al más caro: los paneles de IOL
(memo compartido con la ruta de cartera, gratis), `Titulos/{simbolo}/Cotizacion` para lo que los
paneles no traen (1 llamada, con tope de 20 por corrida) y data912 como respaldo público.

Esto reemplaza al mecanismo anterior, que calibraba la escala contra el `Objetivo` del Sheet: un
objetivo a más de ~2.5x del mercado dejaba al instrumento sin precio, y sin objetivo no se cotizaba
nada.

El backfill de **velas** sí sigue calibrando, porque no sale de IOL sino de `analisistecnico`, que
para un CEDEAR puede devolver la acción del NASDAQ en USD (~11x). Su referencia es el último precio
observado en `precios_watchlist` — un precio real, no una intención.

Un ticker que además está en cartera toma su precio de la serie normal (`precios_instrumento`), no
de este mecanismo.

### Objetivo de compra

A diferencia de `Objetivo Modo/Valor` de `Instrumentos` (que es un precio de **venta**, se cruza
hacia arriba), el objetivo de la Watchlist es un precio de **compra**: la alerta se dispara cuando
el precio de mercado baja hasta ese nivel o por debajo (misma mecánica que el stop-loss). Siempre es
un valor fijo, nunca un porcentaje: acá no hay precio de compra previo del que partir. El margen de
aviso ("cerca") es el umbral global de Ajustes → Alertas de precio, el mismo que usan las
posiciones.

Se ve en "Más" → "Watchlist", con badge de alertas ahí y un bloque "Oportunidades de compra" en
Resumen. Sus tickers entran además al universo de Análisis técnico y del Screener (`origen:
"watchlist"`).

### Endpoints

```
GET    /api/inversiones/catalogo?q=&tipo=&limite=
GET    /api/inversiones/watchlist
POST   /api/inversiones/watchlist                  {ticker, objetivo?, notas?}   201 / 404 / 409
PUT    /api/inversiones/watchlist/{ticker}         {objetivo?, notas?}
DELETE /api/inversiones/watchlist/{ticker}
POST   /api/inversiones/watchlist/{ticker}/precio  refresca uno
POST   /api/inversiones/watchlist/precios          refresca todos
```

## Rebalanceo de Cartera

La pestaña opcional `Rebalanceo` define los porcentajes objetivo de asignación de la
cartera, en 3 ejes independientes (cada uno suma 100% por su cuenta). Debe coincidir
exactamente en el Google Sheet y en `sheet_local/sheet_inversiones.xlsx`. No es lo mismo
que `Objetivo Modo/Valor` de `Instrumentos` (eso es el precio objetivo de venta de un
ticker puntual, no tiene relación con esta pestaña).

| Columna | Valores | Significado |
|---|---|---|
| `Cartera` | nombre de cartera, `Consolidado`, o vacío | A qué alcance aplica el objetivo. Vacío/`Consolidado` = patrimonio total. |
| `Eje` | `Cartera`, `Tipo` o `Sector` | Qué se está repartiendo. `Cartera` solo es válido con `Cartera` vacío/`Consolidado`. |
| `Categoría` | texto libre | Nombre de la cartera (eje `Cartera`), del Tipo Instrumento o del Sector, según corresponda. |
| `Porcentaje Objetivo` | número 0-100 | % objetivo dentro de ese eje y ese alcance. |

Si no se define una fila para una categoría con valor invertido real, esa categoría se
muestra en la app como "Sin objetivo" (con su valor/% actual, sin comparación). Si la
pestaña no existe todavía, la sincronización no falla — simplemente no hay objetivos
cargados. Se ve en la pestaña "Rebal." del nav inferior.

