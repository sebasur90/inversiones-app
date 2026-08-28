# Pendiente — punto de retomada

> Handoff corto para retomar el plan de mejoras sin re-explorar el repo.
> El catálogo completo y priorizado está en **`PLAN_MEJORAS_PENDIENTES.md`** (leer ese primero).

_Actualizado: 2026-08-28_

## Estado

- Todo lo hecho está en **`main`**, **sin pushear** (`main` está 9+ commits adelante de `origin/main`).
- Últimos commits relevantes:
  - Ola 5 ítem 5: **Vista fiscal por año** (`get_vista_fiscal_por_anio` +
    `pages/VistaFiscal.tsx`, ruta `/vista-fiscal`). Realizado / ingresos / comisiones por año
    calendario, USD y ARS, desglose por ticker, export CSV. Misma convención de costo promedio
    que `get_pnl_realizado_no_realizado`.
  - `3a4b9ec` — Ola 4: **Precios automáticos de acciones y CEDEARs** (data912
    `/live/arg_stocks` + `/live/arg_cedears`). Ver detalle en `PLAN_MEJORAS_PENDIENTES.md`.
  - `9266157` — Ola 3 ítem 1b: **Backfill histórico de precios de renta fija**
    (`market_data/analisistecnico.py` + `precios.fetch_backfill_renta_fija_api`).
  - `14077b7` — Ola 3 ítem 3: **Vencimientos enriquecido** (paridad, TIR al vto., duration,
    "% de la cartera que vence por año").
  - `a60ffe0` — Ola 3 ítem 2: pantalla **Flujo de caja proyectado**.
  - `4f8eb9c` / `f29123e` — Ola 3 ítem 1: precios automáticos de renta fija (data912).
  - `0316e24` — Ola 1-2: market_data (CER/MEP/inflación) + menú "Más".
- Tests backend: **272 pasan, 0 fallan** (+25 con Ola 4; +7 con Ola 5 ítem 5:
  `test_vista_fiscal_por_anio.py`).
- Ola 4 es puro backend (ingesta en el sync, sin pantalla nueva) — no requiere QA visual.
- QA visual en navegador de Flujo de caja y Vencimientos: **sigue pendiente** (no hubo browser
  en la sesión). Verificado sólo que compila (`tsc && vite build`) y que la salida valida
  contra el schema Pydantic + tests.

## Lo que sigue, en orden

### 1. Ola 3 ítem 1b — Backfill histórico de precios de renta fija  ✅ HECHO

`market_data/analisistecnico.py` (datafeed TradingView UDF de analisistecnico.com.ar, público,
sin auth, `GET /services/datafeed/history?symbol=&resolution=D&from=&to=` → `{s,t,o,h,l,c,v}`,
sin paginar, series frescas al día, escala ARS por lámina de 100 VN igual que data912).
`precios.fetch_backfill_renta_fija_api` puebla `precios_instrumento` (`fuente='api'`) hacia
atrás por cada ticker de renta fija hasta `piso = max(1er movimiento, hoy-5 años)`. Se
auto-limita: no re-pide la serie una vez que las filas `api` llegan a ~el piso
(`_TOLERANCIA_PISO_DIAS=40`), y hay cota de `_MAX_BACKFILL_POR_SYNC=15` peticiones/corrida
(huecos más grandes primero). Reusa la calibración por ratio del ítem 1 (`_factor_escala`).
Sólo emite fechas `< hoy` que el Sheet no cubra (hoy lo maneja la ruta 'live'). Integrado en
`inversiones_sync` en el mismo bloque de precios (upsert compartido con la ruta 'live').
**ONs corporativas**: analisistecnico no las tiene (`{"s":"error"}`) → `SyncIssue` info
`sin_historico_backfill`, siguen forward-only + su historia manual del Sheet. Descartadas para
ONs: `datos.gob.ar` (catálogo viejo), `argen.bond` (API paga), `data912` (no tiene
`/historical/corp`). Pendiente futuro: IOL API (gratis, con OAuth) para cerrar el hueco de ONs.
`UMBRAL_APROXIMADO_DIAS = 45` **sigue** — se saca en un ítem posterior cuando toda la renta
fija tenga cobertura densa.

### 2. Ola 4 — Precios automáticos de acciones y CEDEARs  ✅ HECHO

`data912.fetch_precios_renta_variable()` (`/live/arg_stocks` + `/live/arg_cedears`, ya estaba
escrito) orquestado en `market_data/precios.py`: `fetch_precios_renta_variable_api` comparte
motor con la renta fija (`_fetch_precios_live_api`, parametrizado por predicate/fetch_fn/label)
— modo híbrido, Sheet manda, sólo agrega el precio del día. Clasificación por
`tipo_instrumento`: subcadenas `"accion"`/`"cedear"` sin acentos (`_es_renta_variable`).
Escala calibrada por ratio contra el Sheet igual que el ítem 1 (no se asume 1:1, aunque en la
práctica acciones/CEDEARs suelen cotizar a la par, sin lámina de 100 VN). Integrado en el mismo
bloque de `inversiones_sync`; la purga de filas `api` huérfanas ahora es unión renta
fija+variable. **Sin backfill** — no hay fuente pública de serie diaria para renta variable.
Tests: +25 (240 → 265).

### 3. Ola 5 (sin API, con datos que ya hay)

5. ~~Vista fiscal por año~~ ✅ · 6. TWR bruto vs. neto de comisiones · 7. Historial de calidad
de datos (sparkline health score) · 8. Escenarios (`variacion_por_instrumento` ya en backend,
frontend manda vacío) · 9. Config declarada y no aplicada (`peso_minimo`, `peso_maximo`,
`rendimiento_objetivo`) · 10. Riesgo país + inflación mensual en Indicadores Macro ·
11. Exposición/concentración por país.

### 4. Ola 6 (opcional)

12. Alertas push stop-loss/precio objetivo · 13. Volatilidad implícita/opciones.

### Opcional, no bloqueante (del ítem 2 ya hecho)

Pestaña **`Cronograma`** en el Sheet (`Ticker, Fecha, Tipo, Monto por unidad`) que pise la
proyección inferida de Flujo de caja. Hoy todo es inferencia.

## Higiene de datos detectada, sin tocar

Ver sección homónima en `PLAN_MEJORAS_PENDIENTES.md` (columna sin encabezado en `Precios`,
fila basura en `Configuracion`, `TipoCambio` código muerto, `es_jubilacion` huérfana,
`src/data/glosario.ts` sin uso, `routers/objetivos_inversion.py` sin `_validar_cartera`,
`README.md`/`FUNCIONALIDADES.md` desactualizados, etc.).

## Comandos

```bash
# Tests backend (siempre vía docker compose corporativo, workdir raíz)
docker compose -f docker-compose.yml -f docker-compose.corporate.yml run --rm \
  -v $(pwd):/repo -w /repo -e PYTHONPATH=/repo \
  backend python -m pytest backend/tests/ -q
# Baseline: 265 pasan, 0 fallan

# Build frontend (verifica TypeScript)
docker compose -f docker-compose.yml -f docker-compose.corporate.yml build frontend

# Levantar la app para QA visual
docker compose up
```

## Convenciones a respetar

- Todo corre dentro de contenedores Docker (ver `CLAUDE.md`). No usar chromium.
- Cualquier fetch nuevo a API externa → `backend/app/services/market_data/`: nunca lanza
  (devuelve `None` en fallo), se llama sólo si `market_data.use_external_apis()`, el sync
  distingue "fetch falló → preservar lo que había" de "trajo datos → reemplazar filas
  `fuente='api'`". El Sheet siempre gana.
- Tests de `market_data`/sync **mockean** el fetch (nunca red real; ver
  `backend/tests/conftest.py`).
- Respuestas al usuario: en español.
