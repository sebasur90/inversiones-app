# Plan: serie del subyacente en USD para análisis técnico

## Contexto

Tenés CEDEARs en la watchlist (p.ej. MSFT) y querés correr indicadores y backtests sobre el **precio
real del NASDAQ en USD**, no sobre el CEDEAR local en ARS, sin gastar créditos de IOL.

Hoy pasan dos cosas, las dos malas:

1. **El gráfico local de MSFT está vacío.** `fetch_backfill_ohlcv_watchlist`
   (`backend/app/services/market_data/precios.py:1015-1083`) pide el ticker pelado `MSFT` a
   analisistecnico, recibe la acción de NASDAQ en USD (~500), la compara contra tu `Objetivo` en ARS,
   el ratio cae fuera de las ventanas de `_factor_escala` → issue `escala_desconocida` → **descarta
   todas las velas**. El comentario en `precios.py:1044-1049` ya documentaba el riesgo.
2. **No existe ninguna serie en USD.** No hay mapeo CEDEAR↔subyacente ni ratio de conversión en
   ningún lado del repo.

## Estado real del código (verificado)

Lo que ya está hecho y **no** hay que rehacer:

- `analisistecnico.py` ya parsea OHLCV completo (`fetch_historico_ohlcv` devuelve `BarraCruda` con
  `o/h/l/c/v`); no descarta nada.
- La tabla `serie_ohlcv` (`BarraOHLCV`, `database.py:250`) ya existe, con UNIQUE `(ticker, fecha)`.
- `indicadores_engine.py` (SMA, EMA, RSI Wilder, MACD, Bollinger, ATR, Estocástico, OBV, VolProm) y
  `estrategia_engine.py` (DSL + backtest + presets) ya existen, son puros y reciben `list[Barra]`.
  **No se tocan.**
- `ohlcv_analytics.get_serie_barras` es el único punto de acceso a precios del análisis técnico.

## Fuentes: enfoque híbrido

Medido en vivo, en Docker:

| | analisistecnico | yfinance 1.7.0 |
|---|---|---|
| MSFT cierre 2026-09-04 | 499.70 | **499.70** (coinciden exacto) |
| Profundidad | 1252 barras, desde 2021-09-08 | **10199 barras, desde 1986-03-13** |
| Splits | **sin ajustar** (NVDA 1208.88 → 121.79) | **ajustado** (120.68 → 121.58) + columna `Stock Splits` |
| Pata local | `MSFT:CEDEAR` = 26460 ARS | `MSFT.BA` = 26400 ARS |
| ADR de local | `GGAL:ADR` | `GGAL` = 44.36 USD · `GGAL.BA` = 7005 ARS |
| Auth / API key | no | no |
| Proxy corporativo | `httpx trust_env` (ya integrado) | respeta `HTTP_PROXY` (verificado) |
| Renta fija argentina | sí (soberanos, letras, CER) | no |
| Dependencias nuevas | 0 | ~23 paquetes |

Descartadas y por qué: **Stooq** responde un desafío JS anti-bot (ya estaba en `DESARROLLO.md:97`);
**Yahoo por HTTP crudo** devolvió `Too Many Requests` (necesita cookie+crumb, que es justamente lo que
yfinance encapsula); **Alpha Vantage / Finnhub / Twelve Data** exigen API key con cupos diarios chicos.

### Decisión: yfinance para el subyacente, analisistecnico para lo demás

- **Serie del subyacente en USD → yfinance.** Gana por dos motivos que importan de verdad:
  ajusta splits solo (sin eso, el split 10:1 de NVDA es una caída del 90% en una barra que dispara
  todos los stop-loss del backtest) y da 40 años de historia en vez de 5.
- **Serie local del CEDEAR → analisistecnico con `:CEDEAR`.** Es un fix de una línea sobre la ruta ya
  integrada, y es la fuente contra la que está calibrada la lógica de escala. No se toca lo que anda.
- **Renta fija (soberanos, letras, CER, ONs) → analisistecnico, sin cambios.** Yahoo no tiene nada de
  esto.

### La convención de símbolos de Yahoo es trivial

No hace falta ninguna resolución tipo `/search`: en Yahoo el **ticker pelado es siempre el listado en
EE.UU.** (acción o ADR) y el sufijo **`.BA`** es el listado local en BYMA. Verificado con `MSFT`/
`MSFT.BA`, `AAPL.BA`, `GGAL`/`GGAL.BA`. Esto colapsa entera la etapa de resolución de símbolos que
requería el enfoque anterior.

---

## Implementación

### Paso 0 — Dependencias: pinear pandas (RESUELTO)

`backend/requirements.txt:7` pinea `pandas>=2.2.2` **sin techo**, y una instalación limpia de yfinance
arrastra **pandas 3.0.5**. Pandas 3 trae cambios rompientes (copy-on-write por default) y el lector de
Excel/Sheet usa pandas, así que ese bump era el riesgo #1 del plan.

**Verificado en Docker: yfinance 1.7.0 funciona con pandas 2.3.3** (`MSFT` cierre 499.70, 5 barras).
No hace falta el bump.

```bash
docker run --rm python:3.13-slim sh -c \
  "pip install -q 'pandas>=2.2.2,<3' yfinance && python -c 'import pandas,yfinance as y; print(pandas.__version__, y.Ticker(\"MSFT\").history(period=\"5d\").shape)'"
# -> pandas 2.3.3 yfinance 1.7.0 / barras (5, 7) / ultimo cierre 499.7
```

En `backend/requirements.txt`, cambiar `pandas>=2.2.2` por **`pandas>=2.2.2,<3`** y agregar
**`yfinance>=1.7.0`**. El techo en pandas no es opcional: sin él, la próxima reconstrucción de la
imagen se lleva pandas 3 de arrastre y rompe el sync sin que nadie toque una línea de código.

### Paso 1 — Cliente de yfinance

Nuevo `backend/app/services/market_data/yahoo.py`, con la misma forma de contrato que
`analisistecnico.py` para que el orquestador no note la diferencia:

```python
def fetch_historico_ohlcv(ticker: str, desde: date, hasta: date) -> list[BarraCruda] | None
    """Serie diaria ajustada por splits y dividendos (auto_adjust=True). `None` si falló;
    `[]` si el símbolo existe pero no tuvo ruedas."""

def fetch_info(ticker: str) -> dict | None
    """`{"moneda","mercado","nombre"}` desde `fast_info` (más barato que `.info`).
    Sirve de guarda: sólo se acepta un subyacente con moneda USD."""
```

Tres detalles que no son opcionales:

- **yfinance NO pasa por `client.py`** (hace su propio HTTP con `curl_cffi`). Respeta `HTTP_PROXY` /
  `HTTPS_PROXY` del entorno — verificado —, así que el ambiente corporativo funciona, pero el manejo
  de errores hay que escribirlo acá: envolver todo en `try/except`, devolver `None`, no lanzar nunca.
- **yfinance se traga los errores de red y devuelve un DataFrame vacío**, no una excepción. Un
  resultado vacío es ambiguo entre "no hubo ruedas" y "la red falló": tratar vacío como `None`
  (fallo) salvo que el rango pedido sea genuinamente sin ruedas.
- Convertir el DataFrame a `list[BarraCruda]` acá mismo. El camino de análisis técnico es de listas
  puras de Python; **pandas no entra a `ohlcv_analytics` ni a los engines**.

### Paso 2 — Modelo y migración

En `EstadoMarketDataTicker` (`database.py:157`), para cachear la resolución y no pagar un probe por
ticker por sync:

```
simbolo_subyacente   # "MSFT" (ticker pelado en Yahoo), o NULL si no tiene
mercado_subyacente   # "NMS"/"NYQ" (display)
moneda_subyacente    # "USD" — la que se escribe en serie_ohlcv.moneda
resolucion_estado    # None | 'ok' | 'sin_subyacente' | 'ticker_no_apto'
resolucion_intento   # Date, para el cooldown de 180 días
```

En `EstrategiaTecnica`: `variante` (`'local'` | `'subyacente'`, default `'local'`), porque
`senales_recientes` corre las estrategias guardadas sin que nadie elija nada en la UI.

Migración con el mismo estilo `PRAGMA table_info` + `ALTER TABLE ADD COLUMN` de `init_db()`
(`database.py:314-364`). **Sin reconstruir tablas.**

### Paso 3 — Resolución del subyacente

```python
def resolver_subyacente(activos, estado_por_ticker, hoy=None, max_resoluciones=10) -> list[ValidationIssue]
```

Un solo `fetch_info(ticker)` por ticker de renta variable (`_es_renta_variable`). Se acepta el
subyacente sólo si `moneda == "USD"`. Se cachea; `sin_subyacente` reintenta a los 180 días.

**Riesgo de colisión de tickers — la guarda que importa.** Para un CEDEAR el ticker local *es* el del
subyacente por construcción (así se nombran los CEDEARs), así que la resolución automática es segura.
Para una **acción local** no: el ADR suele tener otro símbolo (`PAMP`→`PAM`, `YPFD`→`YPF`, `TXAR` no
tiene ADR) y el ticker pelado puede resolver a **otra empresa** en Yahoo. Por eso:

- `tipo_instrumento` contiene `cedear` → resolución automática.
- Acción local → sólo se acepta si el `nombre` del instrumento matchea razonablemente el `nombre` que
  devuelve Yahoo; si no, `sin_subyacente` y un issue INFO. Nunca se adivina.

### Paso 4 — Fix de la serie local (desbloquea tu MSFT, valor propio)

En `fetch_backfill_ohlcv_watchlist` (~línea 1005), pedir `{ticker}:CEDEAR` cuando el instrumento es un
CEDEAR, en vez del ticker pelado:

```python
simbolo = (estado_por_ticker or {}).get(ticker, {}).get("simbolo_local") or ticker
serie = analisistecnico.fetch_historico_ohlcv(simbolo, piso_global, ayer)
```

Con `MSFT:CEDEAR` (26460 ARS) el ratio contra el `Objetivo` vuelve a `_RATIO_CERCA_DE_1` → factor 1.0
→ carga sin tocar la lógica de calibración. `escala_desconocida` deja de dispararse.

Saneamiento: si el símbolo local cambió respecto del último usado, borrar las velas locales viejas del
ticker antes del upsert (pueden estar en la unidad equivocada). Se dispara una sola vez.

### Paso 5 — Almacenamiento del subyacente: clave derivada

En `ohlcv_analytics.py`:

```python
SUFIJO_SUBYACENTE = "@SUB"
def clave_serie(ticker: str, variante: str = "local") -> str   # "MSFT" -> "MSFT@SUB"
def ticker_base(clave: str) -> str
```

**Por qué clave derivada y no una columna discriminadora:** el UNIQUE de `serie_ohlcv` es
`(ticker, fecha)` y SQLite no permite alterarlo — habría que reconstruir la tabla, la única migración
del repo capaz de perder datos, sobre historia cara de rebajar. Además tiene una propiedad emergente
valiosa: **`MSFT@SUB` no existe en `precios_instrumento`**, así que la contaminación ARS↔USD en el
merge de `get_serie_barras` es imposible por construcción, no sólo por un `if`.

En `precios.py`:

```python
def fetch_backfill_ohlcv_subyacente(activos, ohlcv_existentes, ohlcv_maximos,
                                    estado_por_ticker, hoy=None, max_llamadas=12)
        -> tuple[list[dict], list[ValidationIssue]]
```

Emite filas con `ticker=clave_serie(t,"subyacente")`, `moneda="USD"`, `fuente="yahoo"` — hay que
**agregar `"yahoo"` a `_PRIORIDAD_FUENTE`** (`ohlcv_analytics.py:37`) o las barras nunca ganan un
upsert (una fuente desconocida ordena `-1`). Sin `db`, sin fallback a IOL.

Dos trabajos priorizados dentro del cupo: **(1) refresco de cola** — esta serie no tiene ruta *live*
que le escriba el cierre del día, a diferencia de la local, así que sin esto se congela; **(2)**
backfill hacia atrás hasta `_PISO_SUBYACENTE` (5 años; yfinance da todo en una sola llamada, así que
el piso es una decisión de cuánto guardar, no un límite de la fuente).

**No pasa por `_factor_escala`, a propósito.** Esa función reconcilia una serie con el precio de
referencia *local* (Sheet / `Objetivo`). El subyacente es otro instrumento, en otro mercado, en otra
moneda, bajo otra clave: calibrarlo contra ARS es justamente el bug de hoy. Se reemplaza por:
**G1** sólo se baja si `fetch_info` confirmó `moneda == "USD"`; **G2** la moneda sale de la fuente,
nunca del Sheet ni del `WatchlistItem`; **G3** cordura (≥2 barras, cierres finitos y positivos);
**G4** aislamiento de escritura — sólo `serie_ohlcv`, que ningún analytic de patrimonio, exposición o
riesgo lee.

### Paso 6 — Lectura

```python
def get_serie_barras(ticker, desde, hasta, db, barras_previas=0,
                     max_barras=MAX_BARRAS_DEFAULT, variante: str = "local") -> dict
def variantes_de_ticker(db) -> dict[str, list[dict]]   # sólo las variantes con filas reales
```

- `variante` es kwarg con default: los llamadores actuales no cambian, y `cache_por_sync` ya lo mete
  en la clave, así que local y subyacente no comparten entrada de caché.
- Guard explícito: con `variante == "subyacente"` **no se mergea `PrecioInstrumento`** (son cierres
  ARS del CEDEAR; mezclarlos daría un salto de ~x50 entre barras contiguas).
- La `moneda` del dict sale de la serie, no del instrumento (que está declarado en ARS), y
  `moneda_mixta` deja de dispararse espuriamente.
- `listar_tickers_tecnicos` suma `"series": [{variante, moneda, mercado}]` (siempre incluye `local`).
- **Reescribir la docstring del módulo (línea ~19)**, que hoy dice sin matices "No se convierte a
  USD". La política no cambia — esta feature *no convierte*, lee una serie que ya cotiza nativamente
  en USD, que es otra cosa. Es el comentario que un lector futuro va a usar para decidir si esto es un
  bug.

### Paso 7 — Sync, purga y presupuestos

- Cargar y persistir las claves nuevas **en los dos lugares** de `inversiones_sync.py` (~388 y ~660):
  el loop de persistencia asigna con `est.get(...)`, así que una clave faltante escribiría `None` y
  borraría la caché de resolución en cada sync.
- Agregar `ohlcv_maximos` al agregado de la línea ~401 (`func.max(BarraOHLCV.fecha)` junto al `min`).
- **Purga de huérfanos (~línea 648) — el punto crítico.** Hoy borra todo `BarraOHLCV.ticker` que no
  esté en el Sheet; sin whitelistear las claves derivadas **borraría la serie del subyacente entera en
  cada sync**:
  ```python
  tickers_ohlcv_validos = tickers_base | {clave_serie(t, "subyacente") for t in tickers_base}
  ```
- El upsert (líneas 606-643) no cambia: `debe_reemplazar_barra` opera por `(ticker, fecha)`.
- `_MAX_BACKFILL_OHLCV_POR_SYNC = 8` **no se toca**: cuenta sólo llamadas IOL, y este camino nunca
  llama a IOL.

### Paso 8 — API y frontend

`schemas.py` (~1092-1224): `SerieVarianteOut` nuevo; `variante`/`mercado` en `SerieTecnicaOut`;
`series` en `TickerTecnicoOut`; `variante` en `BacktestRequest`, `EstrategiaGuardarRequest`,
`EstrategiaOut`; `variante`+`moneda` en `BacktestOut` y `SenalTickerOut`.

`routers/tecnico.py`: `?variante=` en `GET /tecnico/{ticker}/serie`; la variante del backtest va **en
el body**, no en el path, para que la clave `@SUB` nunca salga del backend y `_validar_ticker_tecnico`
siga intacto. 422 si la variante no existe, 404 si el ticker no tiene serie de subyacente.

`estrategias_analytics.py`: `variante` en `ejecutar_backtest`, en el CRUD (se arrastra al duplicar) y
en `senales_recientes`, que la lee de la estrategia guardada.

Frontend — `frontend/src/pages/AnalisisTecnico.tsx` y `frontend/src/components/tecnico/`:

- Toggle `Segmented` `Local (ARS) / Subyacente (USD)`, sólo si `series.length > 1`, con variante
  efectiva derivada (no `useEffect`, para que no haya flash al cambiar de ticker) y fallback a `local`.
- `variante` en la `queryKey` y en `getSerieTecnica` / `backtestEstrategia` / `guardarEstrategia`. Al
  cargar una estrategia guardada, sincronizar el toggle con su `variante`.
- **Mostrar la moneda** — hoy la pantalla no la muestra en ningún lado, y ése es el riesgo #1 de leer
  499.70 como si fueran pesos: badge junto al toggle, prefijo en el hover OHLC y en el eje de
  `PanelPrecio`, y en el título del fullscreen.
- `Watchlist.tsx` consume `/tecnico/senales`: el badge de señal ahora puede traer un precio en USD →
  mostrar la moneda.

---

## Verificación

Todo en Docker, nunca en el host.

```bash
docker compose run --rm --no-deps -v "$PWD/backend":/app backend python -m pytest tests -q

docker compose up -d --build
curl -s -X POST localhost:8000/api/inversiones/sync
curl -s "localhost:8000/api/inversiones/tecnico/tickers" | jq '.[] | select(.ticker=="MSFT")'
curl -s "localhost:8000/api/inversiones/tecnico/MSFT/serie?variante=subyacente&indicadores=SMA(200)" \
  | jq '{moneda, mercado, variante, n:(.barras|length), ultima:.barras[-1], advertencias}'
curl -s "localhost:8000/api/inversiones/tecnico/MSFT/serie?variante=local" \
  | jq '{moneda, n:(.barras|length), ultima:.barras[-1]}'
```

**Criterio de aceptación**: `variante=subyacente` devuelve barras en **USD** con cierres del orden de
500; `variante=local` devuelve barras en **ARS** del orden de 26.000 (hoy devuelve cero); un segundo
sync no re-resuelve símbolos ni re-baja series ya convergidas.

**Chequeo de splits**: `GET /tecnico/NVDA/serie?variante=subyacente&desde=2024-01-01` **no** debe
mostrar una caída del 90% el 2024-06-10 (yfinance ya lo entrega ajustado: 120.68 → 121.58), y un
backtest de `cruce_medias` sobre NVDA no debe tener una operación disparada ese día.

## Tests

Estilo del repo: pytest plano, `monkeypatch` sobre el cliente, **nunca red real**.

| Archivo | Qué cubre |
|---|---|
| `test_yahoo.py` *(nuevo)* | DataFrame → `list[BarraCruda]`; DataFrame vacío → `None`; excepción de red → `None`; `fetch_info` con moneda no-USD |
| `test_market_data_subyacente.py` *(nuevo)* | MSFT resuelve con `moneda=="USD"`; un `fetch_info` que devuelve ARS **rechaza** el subyacente (G1); acción local sin match de nombre → `sin_subyacente`; la resolución no se repite si ya está `'ok'`; el backfill emite `MSFT@SUB` con `moneda=="USD"` y precios verbatim aunque haya un `factor_escala` persistido |
| `test_market_data_ohlcv_backfill.py` | **Regresión del bug**: CEDEAR con `Objetivo` en ARS y símbolo `MSFT:CEDEAR` → hay velas y **no** hay `escala_desconocida` |
| `test_ohlcv_analytics.py` | `variante="subyacente"` lee `@SUB` y **no** mergea `PrecioInstrumento`; `moneda=="USD"`; sin `moneda_mixta`; local y subyacente no comparten entrada de caché; `"yahoo"` gana el upsert donde corresponde |
| `test_tecnico_router.py` | `series` en `/tecnico/tickers`; `?variante=subyacente` 200 / 404 sin serie / 422 inválida; backtest con `variante` en el body |
| `test_inversiones_sync_market_data.py` | **La purga NO borra `MSFT@SUB`** mientras MSFT esté en watchlist, y **sí** cuando sale; ninguna fila `@SUB` llega a `precios_instrumento`; el estado de resolución sobrevive dos syncs |

## Riesgos y bordes

1. **Arrastre de pandas 3.x** — descartado: yfinance anda con pandas 2.3.3. Queda como riesgo latente
   sólo si se afloja el techo `<3` del Paso 0.
2. **yfinance es scraping no oficial de Yahoo**: se rompe cada tanto y se arregla actualizando la
   librería. Mitigación: es una fuente *auxiliar* — si falla, la serie local y toda la valuación
   siguen andando; sólo se congela la pestaña del subyacente.
3. **Rate limiting de Yahoo**: un `curl` crudo ya comió un `Too Many Requests`. yfinance maneja
   cookie+crumb, y el sync es de baja frecuencia, pero el cupo por corrida (12) existe por esto.
4. **Colisión de tickers** en acciones locales (el pelado puede ser otra empresa en Yahoo). Mitigado
   con el match de nombre del Paso 3; para CEDEARs no aplica.
5. **La serie local sigue sin ajustar por splits.** Un cambio de ratio de conversión del CEDEAR
   produce el mismo salto que un split. Alcance actual: **detectar y advertir** (`posible_cambio_de_ratio`),
   no ajustar. Si molesta en la práctica, la salida es mover también la pata local a yfinance
   (`MSFT.BA`, ya verificado que funciona y viene ajustado).
6. **La serie `@SUB` no tiene ruta live**: sin el refresco de cola del Paso 5 se congelaría en la
   última barra bajada.
7. **`ALL`/`3Y` muestran distinta historia en cada variante** (yfinance llega a 1986, la local a 2021).
   Es correcto; alcanza con que el gráfico muestre la fecha de la primera barra.
8. **Señales con monedas mezcladas**: las métricas del backtest son porcentuales y siguen siendo
   comparables entre variantes; los **precios** de entrada/salida no. Mitigado mostrando la moneda.
9. **Cero impacto en valuación**: ninguna fila nueva toca `precios_instrumento` ni `precios_watchlist`;
   patrimonio, exposición y riesgo no leen `serie_ohlcv`.
10. **Cero créditos IOL**: todo el camino nuevo es yfinance + analisistecnico, gratis y sin auth.

## Estado

Plan listo para implementar. Sin bloqueantes: la compatibilidad de pandas quedó verificada y el
Paso 4 (fix de la serie local) tiene valor propio y se puede entregar solo, antes que el resto.
