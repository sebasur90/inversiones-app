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

La pestaña `Instrumentos` admite 4 columnas opcionales para fijar, por ticker, un precio
objetivo (para tomar ganancias) y un stop loss (para cortar pérdidas). Deben coincidir
exactamente en el Google Sheet y en `sheet_local/sheet_inversiones.xlsx`:

| Columna | Valores | Significado |
|---|---|---|
| `Objetivo Modo` | `Porcentaje` o `Fijo` | cómo interpretar `Objetivo Valor` |
| `Objetivo Valor` | número | `Porcentaje`: % sobre el precio promedio de compra (ej. `20` = +20%). `Fijo`: precio absoluto |
| `Stop Loss Modo` | `Porcentaje` o `Fijo` | cómo interpretar `Stop Loss Valor` |
| `Stop Loss Valor` | número | `Porcentaje`: % de caída sobre el precio promedio de compra (ej. `-5`). `Fijo`: precio absoluto |

`Modo` y `Valor` deben completarse juntos (o dejarse ambos vacíos). Se ven en el detalle de
cada ticker en la app, junto con el % que falta para alcanzarlos.

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

