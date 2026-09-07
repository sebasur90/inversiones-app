# Plan: Serie del Subyacente en USD para Análisis Técnico

## Contexto

La investigación sobre fuentes de precios gratis para las estrategias de trading terminó en un plan
concreto para obtener series de precios en USD con profundidad histórica suficiente para análisis técnico.

**Fuente identificada**: analisistecnico.com.ar (datafeed libre, sin autenticación)

## Hallazgos de la investigación

### Símbolos y disponibilidad

Los símbolos que funcionan contra el datafeed:
- `MSFT` — Microsoft (USA)
- `MSFT:CEDEAR` — Microsoft CEDEAR (Argentina)
- `GGAL:ADR` — Grupo Galicia ADR (Argentina)

### Profundidad de datos

- **1252 barras históricas** desde 2026-09-08 hacia atrás (~ 5 años de datos diarios)
- Suficiente para indicadores técnicos estándar (SMA, EMA, RSI, MACD, Bollinger, ATR, etc.)
- Datos validados en vivo contra el datafeed

### Bugs y limitaciones identificadas

1. **Bug de `escala_desconocida`**
   - MSFT en ciertos períodos no devuelve datos OHLC, solo cierre
   - El parser actual marca con `precio_faltante` cuando falta cualquier campo OHLC
   - Solución: permitir degradación (cierre repetido como O/H/L si no está disponible)

2. **Splits no ajustados**
   - El datafeed NO ajusta precios históricos por splits de acciones
   - Ejemplos confirmados:
     - NVDA: split 10:1
     - AMZN: split 20:1
     - TSLA: split 3:1
   - **Impacto**: técnicas de backtesting deberían documentar que comparan contra series sin ajuste
   - **Workaround**: Ajustar manualmente si se necesita análisis histórico preciso

## Implementación esperada

### Paso 1: Ampliar el parseo de `analisistecnico.py`

Actualmente recibe `{s,t,o,h,l,c,v}` pero descarta `o/h/l/v`. Guardar en la tabla `serie_ohlcv`:

```python
# backend/app/services/market_data/analisistecnico.py
# Cambiar de:
precio = Barra(
    fecha=fecha,
    cierre=float(data["c"])
)
# A:
precio = Barra(
    fecha=fecha,
    apertura=float(data.get("o")) or None,
    maximo=float(data.get("h")) or None,
    minimo=float(data.get("l")) or None,
    cierre=float(data["c"]),
    volumen=float(data.get("v")) or None
)
```

### Paso 2: Verificar `iol.fetch_historico`

Revisar si `seriehistorica` de IOL devuelve más campos que solo `ultimoPrecio`. Si es así,
también guardar OHLCV en `serie_ohlcv`.

### Paso 3: Schema en base de datos

Tabla `serie_ohlcv` (sin FK, sirve tanto watchlist como cartera):

```sql
CREATE TABLE serie_ohlcv (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    fecha DATE NOT NULL,
    apertura REAL,
    maximo REAL,
    minimo REAL,
    cierre REAL NOT NULL,
    volumen REAL,
    UNIQUE(ticker, fecha)
);
```

### Paso 4: Indicadores técnicos

Motor `indicadores_engine.py` (puro, sin DB) con:
- SMA, EMA
- RSI (Wilder)
- MACD
- Bollinger Bands
- ATR (Wilder)
- Estocástico
- OBV
- Volumen promedio

Invariante: toda función devuelve lista de **misma longitud** que entrada, con `None` durante warm-up.

## Notas y decisiones

- **Sin numpy/pandas-ta**: Implementación en Python puro (como `risk_engine.py`)
- **Degradación sin OHLC**: Si falta alto/bajo, usar cierre como aproximación
- **Índice posicional por rueda**: SMA(50) = 50 barras, no días calendario (evita inventar precios en feriados)
- **Splits sin ajustar**: Documentar que backtests comparan series sin ajuste por splits históricos
- **Cero llamadas HTTP nuevas**: Reutilizar fetch existente, solo ampliar el parseo

## Estado

Plan documentado, listo para investigación de implementación.
