# Pendiente — punto de retomada

> Handoff corto para retomar el plan de mejoras sin re-explorar el repo.
> El catálogo completo y priorizado está en **`PLAN_MEJORAS_PENDIENTES.md`** (leer ese primero).

_Actualizado: 2026-08-28_

## Estado

- Todo lo hecho está en **`main`**, **sin pushear** (`main` está 4 commits adelante de `origin/main`).
- Últimos commits relevantes:
  - `a60ffe0` — Ola 3 ítem 2: pantalla **Flujo de caja proyectado** (recién hecho).
  - `4f8eb9c` / `f29123e` — Ola 3 ítem 1: precios automáticos de renta fija (data912).
  - `0316e24` — Ola 1-2: market_data (CER/MEP/inflación) + menú "Más".
- Tests backend: **214 pasan, 0 fallan**.
- QA visual en navegador de la pantalla nueva: **pendiente** (no hubo browser en la sesión).
  Verificado sólo que compila (`vite build`) y que la salida valida contra el schema Pydantic.

## Lo que sigue, en orden

### 1. Ola 3 ítem 3 — Vencimientos enriquecido  ← SIGUIENTE

Sobre `frontend/src/pages/Vencimientos.tsx` y su endpoint (`get_vencimientos` en
`backend/app/services/inversiones_analytics.py:2010`). Agregar por instrumento:

- **Paridad**: precio de mercado vs. valor técnico (precio / valor técnico).
- **TIR al vencimiento**: reutilizar `_calcular_xirr` (`inversiones_analytics.py:601`) aplicado
  al flujo proyectado. Ese flujo ya lo arma
  `flujo_caja_analytics.get_flujo_caja_proyectado()` (cobros de cupón + amortización con
  fecha y monto) — se puede exponer una variante que devuelva los cobros crudos por ticker,
  o reconstruir el flujo desde `instrumentos[].proximo_cobro` + la periodicidad.
- **Duration modificada** (a partir del mismo flujo).
- Resumen **"% de la cartera que vence por año"**.

Ojo: la proyección del ítem 2 es *inferida* del historial de cupones; la TIR/duration que
salga de ahí hereda esa incertidumbre → marcarlo en la UI igual que en Flujo de caja.

### 2. Ola 3 ítem 1b — Backfill histórico de precios de renta fija

`data912 /historical/bonds/{ticker}` para poblar hacia atrás la serie `precios_instrumento`
con `fuente='api'` (hoy sólo crece hacia adelante desde que se prende `USE_EXTERNAL_APIS`).
Patrón: `backend/app/services/market_data/precios.py`.

### 3. Ola 4 — Precios automáticos de acciones y CEDEARs

`data912 /live/arg_stocks` + `/live/arg_cedears`, modo híbrido (Sheet manda, API rellena).
Ya existe `data912.fetch_precios_renta_variable()` escrito; falta la orquestación estilo
`precios.py` y la integración al sync. Mismo cuidado con el mapeo de tickers y la escala
(lámina) que en el ítem 1.

### 4. Ola 5 (sin API, con datos que ya hay)

5. Vista fiscal por año · 6. TWR bruto vs. neto de comisiones · 7. Historial de calidad de
datos (sparkline health score) · 8. Escenarios (`variacion_por_instrumento` ya en backend,
frontend manda vacío) · 9. Config declarada y no aplicada (`peso_minimo`, `peso_maximo`,
`rendimiento_objetivo`) · 10. Riesgo país + inflación mensual en Indicadores Macro ·
11. Exposición/concentración por país.

### 5. Ola 6 (opcional)

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
# Baseline: 214 pasan, 0 fallan

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
