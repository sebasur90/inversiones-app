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

1. **Precios automáticos de bonos/ONs/letras** — `data912`: `/live/arg_bonds`,
   `/live/arg_corp`, `/live/arg_notes`, `/historical/bonds/{ticker}`. Requiere resolver el
   mapeo de tickers entre la nomenclatura del Sheet y la del proveedor (reportar los no
   mapeados como `SyncIssue` informativo, nunca adivinar). Junto con el ítem 4 de Ola 4,
   elimina la carga manual de la pestaña `Precios` y el `UMBRAL_APROXIMADO_DIAS = 45` que hoy
   marca posiciones como "precio desactualizado".
2. **Pantalla nueva: Flujo de caja proyectado** — cuánto se va a cobrar por mes en los próximos
   12-24 meses (cupones + amortizaciones), apilado por instrumento. No hay API gratuita de
   cronogramas de bonos argentinos: inferir la periodicidad de la historia de cupones ya
   cobrados por ticker (frecuencia + monto por unidad) y proyectarla hasta el vencimiento;
   marcar en la UI qué está inferido. Opcionalmente, una pestaña `Cronograma` en el Sheet
   (`Ticker, Fecha, Tipo, Monto por unidad`) que pise lo inferido.
3. **Vencimientos enriquecido** — sobre `pages/Vencimientos.tsx`: paridad (precio vs. valor
   técnico), TIR al vencimiento (reutilizar `_calcular_xirr`,
   `inversiones_analytics.py:601`, aplicado al flujo del ítem 2), duration modificada, resumen
   "% de la cartera que vence por año".

### Ola 4 — el resto de los precios

4. **Precios automáticos de acciones y CEDEARs** — `data912 /live/arg_stocks` y
   `/live/arg_cedears`, modo híbrido (Sheet manda, API rellena). Mismo cuidado con el mapeo de
   tickers que en el ítem 1.

### Ola 5 — información nueva con los datos que ya hay (sin API)

5. **Pantalla nueva: Vista fiscal por año** — agrupar `get_pnl_realizado_no_realizado`
   (`inversiones_analytics.py:1640`) por año calendario: realizado, dividendos/cupones
   cobrados, comisiones pagadas, en ARS y USD, con export CSV.
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
- `FUNCIONALIDADES.md` dice 14 pantallas; ahora son 22 (21 + "Más").

## Notas técnicas para retomar

- **Tests**: siempre vía docker compose corporativo, workdir raíz:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.corporate.yml run --rm \
    -v $(pwd):/repo -w /repo -e PYTHONPATH=/repo \
    backend python -m pytest backend/tests/ -q
  ```
  Baseline actual: **176 pasan, 0 fallan**.
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
