# Plan de mejoras — pendiente

Catálogo priorizado de información y pantallas nuevas para la app, armado a partir de una
revisión completa del backend/frontend/datos (agosto 2026). Se ejecutó **Ola 1 completa** y
**Ola 2 con alcance ajustado** (ver abajo por qué). Este documento retoma desde ahí.

Plan original completo (con el detalle de cada ítem, esfuerzo/valor estimado, y las APIs
candidatas evaluadas): `/home/slrodriguez/.claude/plans/teniendo-en-cuenta-todo-glittery-flurry.md`
(fuera del repo — sólo en esta máquina). Este archivo es la versión resumida y actualizada con
lo que ya se hizo.

## Contexto

El cuello de botella de la app no es el cálculo (hay un backend analítico muy completo: XIRR,
TWR, Sharpe/Sortino/Calmar, alpha/beta, HHI, correlaciones, descomposición FX, opportunity
cost, motor de escenarios) sino la **entrada de datos**: precios, CER, MEP y benchmarks se
cargaban a mano porque el backend no hacía ninguna llamada HTTP externa.

Decisiones que enmarcan el plan (del usuario):
- Preferir API gratuita y confiable sobre carga manual, reemplazando el valor manual cuando
  exista fuente automática.
- Correr en dos ambientes: corporativo con proxy (desarrollo) e internet libre (uso real) →
  flag `USE_EXTERNAL_APIS` + degradación limpia si la red falla.
- La renta fija (bonos, ONs, letras) es parte importante de la cartera → prioridad alta a
  flujo de caja proyectado y métricas de bonos (Ola 3).

## Ya hecho (Ola 1 completa + Ola 2 ajustada)

- **`backend/app/services/market_data/`** (nuevo): cliente `httpx` (`trust_env=True`, respeta
  proxy corporativo) con User-Agent de navegador — ArgentinaDatos y DolarAPI devuelven 403 al
  UA por defecto de Python. Providers: `argentina_datos.py` (UVA, MEP histórico, inflación
  mensual), orquestación en `indices.py`.
- Flag `USE_EXTERNAL_APIS` (default `true` en ambos `docker-compose*.yml`). Apagado, la app se
  comporta exactamente como antes. Prendido: la API completa huecos, **el Sheet siempre gana**
  (columna `fuente`: `sheet`|`api` en `IndiceMercado` y `BenchmarkValor`). Si la API falla, no
  rompe el sync: advertencia en Calidad de datos, se preserva lo último bueno.
- Se lee la pestaña **`Tipos de Cambio`** (existía en el Excel, el código nunca la leía) —
  `services/validation/reglas_tipos_cambio.py`, tiene prioridad sobre las columnas CER/MEP
  embebidas en Movimientos/Precios.
- `IndiceMercado` se completa con **serie diaria de CER (vía UVA) y MEP** automática.
- Benchmark automático real **"Inflación (INDEC)"** — verificado en vivo: activa
  PerformanceRelativa, BenchmarksComparacion, Sharpe de Riesgo y opportunity-cost con datos
  reales (antes sólo había "MERVAL" con 2 puntos, prácticamente inútil).
- Cualquier ticker con precio es seleccionable como benchmark en Riesgo/PerformanceRelativa
  (`useBenchmarkSeleccionado.ts`) — el backend ya lo soportaba, sólo faltaba exponerlo.
- Menú **"Más"** (`pages/Mas.tsx`, ruta `/mas`, reemplaza "Precios" en el bottom nav): agrupa
  las 13 pantallas que sólo se alcanzaban por links contextuales.
- Tile **"Efecto de tus aportes"** (XIRR − TWR) en Rendimiento.
- 176 tests pasando (163 → 176; nuevo `backend/tests/conftest.py` fuerza
  `USE_EXTERNAL_APIS=false` por default en toda la suite, para que los tests nunca dependan de
  la red real).

**Quedó explícitamente descartado** (no hay API gratuita confiable, documentado en
`DESARROLLO.md`): benchmark MERVAL automático, benchmark S&P 500 (Stooq bloquea con un
desafío JS), tasa libre de riesgo histórica para Sharpe (el endpoint de plazo fijo de
ArgentinaDatos sólo da la tasa *actual*, no serie histórica; `fci/mercadoDinero/{fecha}`
tampoco respondió en la prueba). Si en algún momento aparece una fuente viable, retomar acá.

## Pendiente, priorizado

### Ola 3 — renta fija (la parte que el usuario marcó como importante)

1. ~~**Precios automáticos de bonos/ONs/letras**~~ — ✅ HECHO (`market_data/data912.py` +
   `market_data/precios.py`, columna `precios_instrumento.fuente`, integrado en el sync).
   `/live/arg_bonds` + `/live/arg_corp` + `/live/arg_notes`; match por símbolo exacto, los no
   encontrados son `SyncIssue` info (tab "Precios (API)"), nunca se adivina. Escala data912
   (lámina de 100 VN) vs. Sheet (1 VN) resuelta **por ratio observado contra el último precio
   manual** de cada ticker (decisión del usuario 2026-08-28): factor ≈100 o ≈1, cualquier otro
   ratio no se carga y se reporta; sin precio previo en el Sheet tampoco se carga. Sólo se
   agrega el precio del día (los `/live/*` son foto intradiaria); las filas `fuente='api'`
   acumulan histórico. Junto con el ítem 4 de Ola 4, apunta a eliminar la carga manual de
   `Precios` y el `UMBRAL_APROXIMADO_DIAS = 45`.

1b. ~~**Backfill histórico de la serie de renta fija**~~ — ✅ HECHO.
   `market_data/analisistecnico.py`: datafeed TradingView UDF de analisistecnico.com.ar
   (público, sin auth) — `GET /services/datafeed/history?symbol={ticker}&resolution=D&from=&to=`
   devuelve `{s,t,o,h,l,c,v}` con arrays paralelos, sin paginar, la serie completa del rango,
   fresca al día, en ARS por lámina de 100 VN (misma escala que data912). `fetch_historico_bono`
   devuelve `None` en fallo / símbolo desconocido (`{"s":"error"}`), `[]` en `{"s":"no_data"}`.
   `precios.fetch_backfill_renta_fija_api` puebla `precios_instrumento` (`fuente='api'`) hacia
   atrás por cada ticker de renta fija hasta `piso = max(fecha del 1er Movimiento del ticker,
   hoy − 5 años)`. **Auto-limitado**: no re-pide la serie de un ticker cuando sus filas `api` ya
   arrancan a ≤ `_TOLERANCIA_PISO_DIAS` (40 d) del piso; cota de `_MAX_BACKFILL_POR_SYNC` (15)
   peticiones por corrida, atendiendo primero los huecos más grandes. Reusa `_factor_escala`
   (calibración por ratio contra el último precio manual del Sheet, extraída del ítem 1); sin
   precio manual → info `sin_precio_para_calibrar`, ratio raro → advertencia `escala_desconocida`.
   Sólo emite fechas `< hoy` que el Sheet no cubra (hoy lo maneja la ruta 'live'). Integrado en
   `inversiones_sync` en el mismo bloque de precios: `api_min_por_ticker` sale de un `query` a
   `PrecioInstrumento.fuente=='api'`, `primeras_fechas_mov` de `movimientos_validos`, y el
   upsert (purga de tickers que dejaron de ser RF + merge por `(ticker, fecha)`) se comparte
   con la ruta 'live'.
   **ONs corporativas**: analisistecnico no las cubre (`{"s":"error"}`) → `SyncIssue` info
   `sin_historico_backfill`; siguen forward-only + su historia manual del Sheet. Fuentes
   descartadas para ONs (2026-08-28): `datos.gob.ar` (catálogo viejo, series cortan ~2019),
   `argen.bond` (API paga), `data912` (`/historical/` sólo tiene `stocks`/`cedears`/`bonds`, no
   `corp` ni `notes`). Opción futura para ONs: IOL API (gratis, requiere cuenta + OAuth).
   `UMBRAL_APROXIMADO_DIAS = 45` **sigue** (follow-up: sacarlo cuando toda la renta fija tenga
   serie densa). Tests: `test_analisistecnico.py` (7), backfill en `test_market_data_precios.py`
   (11), integración en `test_inversiones_sync_market_data.py` (1).
2. ~~**Pantalla nueva: Flujo de caja proyectado**~~ — ✅ HECHO
   (`backend/app/services/flujo_caja_analytics.py`, endpoints
   `/{cartera|consolidado}/flujo-caja-proyectado?meses=`, `frontend/src/pages/FlujoCaja.tsx`,
   ruta `/flujo-caja`, entrada en el menú "Más" grupo Cartera). Proyección mes a mes de
   cupones + amortizaciones, apilada por instrumento, horizonte 12/24/36.
   **Inferencia**: periodicidad = gap mediano entre `cupon` cobrados por ticker (clasificado a
   1/2/3/6/12 meses); monto por unidad = mediana de `precio / tenencia` de cada cupón; la
   grilla se **ancla a la fecha de vencimiento y retrocede** (los cupones caen en fechas fijas
   que terminan el día del vto., anclar al último cupón cobrado desalinea). Confianza
   alta/media/baja (3+ cupones parejos / hay historial / un solo cupón → asume semestral).
   **Capital**: si hay historial de `amortizacion` se infiere y proyecta esa serie
   (`metodo_capital='amortizacion_inferida'`); si no, se asume *bullet* y se estima el capital
   al vto. con `precio_actual * cantidad_actual` de `get_rendimiento_por_ticker`
   (`'bullet'`); sin precio → `'sin_estimacion'`. Bonos sin ningún cupón cobrado no se
   proyectan y van a `sin_proyeccion` con motivo. FX = MEP más reciente (constante).
   Todo lo estimado se marca en la respuesta (`confianza`, `notas`, `metodo_capital`) y en la
   UI. Tests: `backend/tests/test_flujo_caja_analytics.py` (9).
   **Pendiente opcional** (no bloqueante): pestaña `Cronograma` en el Sheet
   (`Ticker, Fecha, Tipo, Monto por unidad`) que pise lo inferido — no implementada; hoy todo
   es inferencia.
3. ~~**Vencimientos enriquecido**~~ — ✅ HECHO. `flujo_caja_analytics.py` ahora expone
   `_proyectar_cobros_ticker` (extraído del ítem 2, mismo motor de inferencia) y
   `get_vencimientos_completo`, que devuelve `{items, por_anio, cartera_valor_*}`. Por
   instrumento se agregan: **paridad** = precio / valor técnico (valor residual + interés
   corrido; residual = par 1, ajustado por el conteo de cuotas de amortización inferidas),
   **TIR al vencimiento** (`_calcular_xirr` sobre `[(hoy, -valor_mercado)] + cobros` de toda
   la vida del bono) y **duration** Macaulay + modificada (misma capitalización que la XIRR).
   Resumen **"% de la cartera que vence por año"** = valor de mercado por año calendario ÷
   `get_resumen`. Todo lo derivado del flujo inferido va marcado (`metricas_estimadas`,
   `metricas_nota`) y la UI lo rotula "est." + nota al pie. `get_vencimientos` sigue
   devolviendo `list[dict]` (lo consume `diagnostico_analytics`); el endpoint cambió a
   `VencimientosOut`. Tests: `backend/tests/test_vencimientos_enriquecido.py` (7).
   **Caveat conocido**: para bonos *bullet* el capital al vto. se estima con el precio de
   mercado actual → la TIR tiende a la TIR corriente (no capta ganancia/pérdida de capital
   contra la par). Se avisa en `metricas_nota` y en el tooltip.

### Ola 4 — el resto de los precios

4. ~~**Precios automáticos de acciones y CEDEARs**~~ — ✅ HECHO. `data912.fetch_precios_renta_variable()`
   (`/live/arg_stocks` + `/live/arg_cedears`, ya estaba escrito desde el ítem 1) orquestado en
   `market_data/precios.py`: `fetch_precios_renta_variable_api` es el mismo motor que
   `fetch_precios_renta_fija_api` (extraído a `_fetch_precios_live_api`, parametrizado por
   predicate/fetch_fn/label) — modo híbrido, Sheet manda, sólo agrega el precio **del día**.
   Clasificación por `tipo_instrumento`: subcadenas `"accion"`/`"cedear"` sin acentos
   (`_es_renta_variable`; sin ambigüedad de tokens sueltos como la "on" de renta fija). Escala:
   igual que el ítem 1, **no se asume 1:1** — se calibra por ratio contra el último precio
   manual del Sheet (`_factor_escala` reusado tal cual), aunque en la práctica las acciones y
   CEDEARs suelen cotizar 1:1 (a diferencia de la lámina de 100 VN de los bonos). Integrado en
   el mismo bloque de `inversiones_sync` que renta fija, compartiendo `claves_sheet` y el
   upsert por `(ticker, fecha)`; la purga de filas `api` huérfanas ahora es unión de tickers de
   renta fija **y** variable (antes sólo miraba renta fija, hubiera borrado esto). **Sin
   backfill histórico** — no hay fuente pública de serie diaria para renta variable (a
   diferencia de analisistecnico para renta fija); sólo crece hacia adelante desde que se activó
   la API. Tests: +25 (`test_data912.py` +3, `test_market_data_precios.py` +9 clasificador +8
   motor, `test_inversiones_sync_market_data.py` +1 mock extendido +3 integración).
   `UMBRAL_APROXIMADO_DIAS = 45` sigue (ver nota del ítem 1b: sacarlo cuando toda la renta fija
   *y* variable tengan cobertura densa — la variable recién empieza a acumular serie).

### Ola 5 — información nueva con los datos que ya hay (sin API)

5. ~~**Pantalla nueva: Vista fiscal por año**~~ — ✅ HECHO.
   `inversiones_analytics.get_vista_fiscal_por_anio` recorre los movimientos por ticker con la
   **misma convención de costo promedio que `get_pnl_realizado_no_realizado`**
   (`_recorrer_movs_ticker`), pero atribuye cada venta/amortización al año de su fecha.
   Devuelve `{por_anio: [...], total: {...}}`; cada año trae `realizado`, `ingresos`
   (dividendos + cupones), `comisiones`, `resultado` (= realizado + ingresos) en USD y ARS
   nominales, más `por_ticker` con el mismo desglose. Las comisiones son la caja pagada en el
   año por **todas** las operaciones (informativo: la comisión de compra está capitalizada en
   el costo y se "realiza" al vender) → **no** se resta de `resultado`. `_monto_*` ya viene
   neto de la comisión de esa operación; ARS se completa con MEP y se acumula sólo cuando hay
   conversión (mismo criterio que el resto). Endpoints
   `/{carteras/{nombre}|consolidado}/vista-fiscal` (`VistaFiscalPorAnioOut`).
   Frontend: `pages/VistaFiscal.tsx`, ruta `/vista-fiscal`, entrada en "Más" grupo Cartera —
   card de resultado acumulado, un card colapsable por año con stat-row realizado/ingresos/
   comisiones y tabla por ticker al expandir, export CSV (una fila TOTAL + una por ticker por
   año). Tests: `backend/tests/test_vista_fiscal_por_anio.py` (7), incl. identidad con
   `get_pnl_realizado_no_realizado`.
6. **Costo real de operar** — `_tasa_comision_promedio` (`inversiones_analytics.py:1260`) ya
   calcula la tasa ponderada; falta mostrar TWR bruto vs. neto de comisiones en Rendimiento.
7. **Historial de calidad de datos** — se guardan 20 `SyncRun`, se expone sólo el último
   (`calidad_datos.py:9`). Agregar sparkline del health score y reglas que se repiten.
8. **Escenarios** — `EscenarioParamsIn.variacion_por_instrumento` está implementado en el
   backend y el frontend lo manda siempre vacío (`Simulador.tsx`); `duplicarEscenario`/
   `eliminarEscenario` existen en `api/index.ts` sin consumidor.
9. **Config declarada y no aplicada** — `peso_minimo` se lee/valida/persiste y
   `rebalanceo_engine.generar_propuesta` nunca lo usa (`rebalanceo_engine.py:80`);
   `peso_maximo` sólo aplica en modo `solo_aportes`; `rendimiento_objetivo` no entra en
   `diagnostico_engine.score_performance`.
10. **Riesgo país e inflación mensual en Indicadores Macro** — riesgo país ya está disponible
    vía ArgentinaDatos (`/v1/finanzas/indices/riesgo-pais`, probado en la exploración), sólo
    falta sumarlo como serie en `IndicadoresMacro.tsx` (no es un benchmark de retorno, es
    información macro).
11. **Exposición y concentración por país** — `InstrumentoInversion.pais` casi sin explotar.

### Ola 6 — opcional

12. **Alertas push** de stop-loss/precio objetivo (ya hay service worker + diagnóstico que
    detecta ambos eventos; sólo tiene sentido después de precios automáticos frescos).
13. **Volatilidad implícita/opciones** — `data912 /eod/volatilities/{ticker}`, nicho.

## Higiene de datos detectada, todavía sin tocar

- Columna sin encabezado en `Precios` (columna H) — se descarta en silencio.
- Fila basura en `Configuracion` (fila con sólo `A2=39`).
- `PrecioInstrumento.moneda` se guarda y se ignora en `get_precios_historicos_ticker`
  (usa `instrumento.moneda`, no `row.moneda`).
- Modelo `TipoCambio` (`database.py`) es código muerto — nadie lo referencia.
- Columna huérfana `es_jubilacion` en `objetivos_inversion` (se agrega por `ALTER TABLE` en
  cada arranque, nadie la lee).
- `src/data/glosario.ts` (30 términos) no lo importa nadie — reemplazado por
  `src/help/content/glosario.ts`.
- `routers/objetivos_inversion.py` no llama a `_validar_cartera` — cartera inexistente
  devuelve 200 con curva vacía en vez de 404.
- `README.md` describe `services/cotizaciones.py`/dolarapi como dependencia — ya no existe tal
  cual (ahora SÍ hay APIs externas reales, pero por `market_data/`, no por ese archivo).
- `FUNCIONALIDADES.md` dice 14 pantallas; ahora son 23 (21 + "Más" + "Flujo de caja proyectado").

## Notas técnicas para retomar

- **Tests**: siempre vía docker compose corporativo, workdir raíz:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.corporate.yml run --rm \
    -v $(pwd):/repo -w /repo -e PYTHONPATH=/repo \
    backend python -m pytest backend/tests/ -q
  ```
  Baseline actual: **272 pasan, 0 fallan** (176 tras Ola 1-2; +29 con Ola 3 ítem 1:
  `test_data912.py`, `test_market_data_precios.py`, 2 de integración en
  `test_inversiones_sync_market_data.py`; +9 con Ola 3 ítem 2:
  `test_flujo_caja_analytics.py`; +7 con Ola 3 ítem 3:
  `test_vencimientos_enriquecido.py`; +19 con Ola 3 ítem 1b: `test_analisistecnico.py` (7),
  backfill en `test_market_data_precios.py` (11), 1 de integración; +25 con Ola 4 ítem 4:
  `test_data912.py` (3), `test_market_data_precios.py` (17), `test_inversiones_sync_market_data.py`
  (3 integración + 1 mock extendido); +7 con Ola 5 ítem 5: `test_vista_fiscal_por_anio.py`).
- **Build frontend** (verifica TypeScript): `docker compose -f docker-compose.yml -f docker-compose.corporate.yml build frontend`.
- Cualquier fetch nuevo a una API externa va en `backend/app/services/market_data/`, con el
  mismo patrón: nunca lanza (devuelve `None` en fallo total), se llama sólo si
  `market_data.use_external_apis()`, y el sync distingue "fetch falló → preservar lo que había"
  de "fetch trajo datos nuevos → reemplazar sólo las filas `fuente='api'`".
- Los tests de `market_data`/sync **mockean** las funciones de fetch — nunca deben pegarle a la
  red real (por eso existe `backend/tests/conftest.py`).
- Pendiente de verificación manual: no se hizo QA visual en navegador del menú "Más" ni de la
  fila "Efecto de tus aportes" (sin herramienta de browser disponible en esta sesión) — sólo se
  verificó que compila y que el build de Vite no rompe. Conviene un vistazo visual con
  `docker compose up` antes de dar por cerrada la Ola 1.
