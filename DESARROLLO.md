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
│       ├── Tipos de Cambio       # Opcional: CER/MEP dedicados (Fecha, Tipo, Valor)
│       └── Watchlist             # Opcional: instrumentos a seguir, ver "Watchlist" más abajo
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
~7 llamadas (1 token + paneles) en régimen normal, más hasta 15 llamadas de backfill mientras hay
historia pendiente de bajar. El contador (tabla `estado_api_iol`, persistido en el volumen
`backend_data`) corta las llamadas a IOL al llegar a `IOL_LIMITE_MENSUAL` (default 22.000, ~12%
de colchón bajo el límite real) y cae a data912 por el resto del mes. `IOL_ENABLED=false` apaga
sólo IOL sin tocar data912/analisistecnico.

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

La pestaña opcional `Watchlist` sirve para seguir instrumentos que **todavía no están en
cartera** (no tienen movimientos) y que se avise cuando el precio se acerca a un precio de
compra. Debe coincidir exactamente en el Google Sheet y en `sheet_local/sheet_inversiones.xlsx`:

| Columna | Valores | Significado |
|---|---|---|
| `Ticker` | texto, requerido | El único campo obligatorio junto con `Objetivo`. |
| `Nombre` | texto | Nombre a mostrar; si falta, se usa el Ticker. |
| `Tipo Instrumento` | texto libre (`Acción`, `CEDEAR`, `Bono`, `ON`, etc.) | Determina si se le busca precio automático (IOL/data912) y en qué familia. |
| `Mercado` | texto | Sólo descriptivo. |
| `Moneda` | `ARS` o `USD` | En qué unidad se muestra el precio; si falta o es inválida, se asume `ARS`. |
| `País` / `Sector` | texto | Sólo descriptivos. |
| `Objetivo` | número | El precio al que se quiere comprar. |

A diferencia de `Objetivo Modo/Valor` de `Instrumentos` (que es un precio de **venta**, se
cruza hacia arriba), el `Objetivo` de la Watchlist es un precio de **compra**: la alerta se
dispara cuando el precio de mercado baja hasta ese nivel o por debajo (misma mecánica que el
stop-loss). El margen de aviso ("cerca") es el umbral global de Ajustes → Alertas de precio,
el mismo que usan las posiciones — la Watchlist no tiene una columna propia para eso.

Los precios automáticos de la Watchlist reusan el mismo motor que los de cartera (IOL primero,
data912 como respaldo), con una diferencia: como estos tickers no tienen precios manuales
previos en `Precios` para calibrar la escala (lámina de 100 VN vs. 1 VN), se usa el propio
`Objetivo` como referencia. Si el objetivo está muy lejos del precio real de mercado (más de
~2.5x en cualquier sentido), el factor de escala no se puede deducir y el precio no se carga
(queda como issue `escala_desconocida` en Calidad de datos); se destraba cargando un precio
manual de ese ticker en la pestaña `Precios`. Un ticker que sí está en cartera toma su precio
de la serie normal (`precios_instrumento`), no de este mecanismo.

Si la pestaña no existe todavía, la sincronización no falla — simplemente no hay watchlist
cargada. Se ve en "Más" → "Watchlist", con badge de alertas ahí y un bloque "Oportunidades de
compra" en Resumen.

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

