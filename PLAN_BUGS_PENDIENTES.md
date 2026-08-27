# Registro de corrección de bugs

Origen: revisión estática completa de backend + frontend (2026-08-26), más una segunda
revisión el 2026-08-27 que encontró 7 bugs de cálculo nuevos (§A).

**Estado: todo cerrado.** Los bugs críticos, altos y medios de la revisión original, los §3
de performance, los 5 tests rotos de §4 y los bloques §A-§D de la segunda revisión están
corregidos y verificados. Baseline de tests: **163 pasan, 0 fallan**.

## Cómo correr las cosas

```bash
# Build (ambiente corporativo, con proxy)
docker compose -f docker-compose.yml -f docker-compose.corporate.yml build backend

# Tests: importan `backend.app.*`, así que necesitan la RAÍZ del repo como workdir
# (el servicio monta la app en /app/app, donde no existe el módulo `backend`).
docker compose -f docker-compose.yml -f docker-compose.corporate.yml run --rm \
  -v $(pwd):/repo -w /repo -e PYTHONPATH=/repo \
  backend python -m pytest backend/tests/ -q
```

**Baseline actual: 163 pasan, 0 fallan.** Cualquier cambio nuevo tiene que mantenerlo en 0.

---

## ✅ Ya corregido y verificado

### De la revisión original

| # | Bug | Archivo |
|---|-----|---------|
| 1 | `_convertir` USD→ARS no devolvía nada (`None` siempre) → toda valuación en ARS de instrumentos USD daba 0 | `backend/app/services/inversiones_analytics.py:47-52` |
| 2 | Crash 500 en Performance Relativa: los `None` de `_calcular_twr_mensual` llegaban a `calcular_beta`/`calcular_tracking_error` | `backend/app/services/benchmarks_analytics.py:190-217` |
| 3 | El sync borraba `IndiceMercado` incondicionalmente, perdiendo el histórico CER/MEP cuando Movimientos o Precios estaban bloqueadas | `backend/app/services/inversiones_sync.py:186-196, 313-317` |

### §1 Prioridad alta (2026-08-27)

| # | Bug | Fix aplicado |
|---|-----|--------------|
| 1.1 | Gráfico del Comparador siempre vacío (fechas fin-de-mes vs día-1 no matcheaban) | `benchmarks_analytics.py`: la serie ahora indexa por `(año, mes)` en vez de por `date` exacto |
| 1.2 | Benchmarks virtuales (MEP/CER/ticker) no resolvían en Riesgo, Performance Relativa y Ticker | Los 3 call-sites que usaban `_benchmark_retornos_mensuales` directo ahora usan `_resolver_fuente` (`riesgo_analytics.py`, `benchmarks_analytics.py:165`, `ticker_analytics.py`) |
| 1.3 | `exceso_retorno` y `tracking_error` eran el mismo número | Nueva `risk_engine.calcular_exceso_retorno_medio` (media anualizada del exceso) separada de `calcular_tracking_error` (desvío) |
| 1.4 | Comisión anualizada se inflaba multiplicando meses parciales | `diagnostico_engine.evaluar_comisiones`: ventana fija de últimos 12 meses calendario (`_ultimos_n_meses`), meses ausentes cuentan como 0, sin extrapolar |
| 1.5 | Amortizaciones rompían la identidad `resumen` ↔ `pnl-realizado` | Convención unificada: amortización = devolución de capital (igual que venta) en `get_resumen`; ya lo era en `get_pnl_realizado_no_realizado` y `_flujos_cashflow`. Test de identidad agregado (`test_amortizacion_identidad.py`) |
| 1.6 | Ticker sin precio actual perdía también su P&L realizado | `get_pnl_realizado_no_realizado`: ahora emite la fila con `no_realizado_* = None` en vez de saltear el ticker |

### §2 Prioridad media (2026-08-27)

| # | Bug | Fix aplicado |
|---|-----|--------------|
| 2.1 | Spinner infinito si el backend no responde | `useInversiones.ts`: `fetchCarteras` con try/catch + `setError` |
| 2.2 | Race condition al cambiar de cartera | `useInversiones.ts`: guard de secuencia (`fetchSeqRef`) descarta respuestas obsoletas |
| 2.3 | `otros_ajustes` hardcodeado en 0 pese al docstring | `patrimonio_analytics.py`: acumula comisiones reales (usd/ars/ars_real) por movimiento; imports muertos (`_monto_bruto`, `_to_usd`, `_convertir`) eliminados; frontend (`Patrimonio.tsx` + `help/content/patrimonio.ts`) muestra la fila "Otros ajustes" y la incluye en el Total |
| 2.4 | Fecha del máximo patrimonial siempre era la de USD | Expuestas `fecha_ars` y `fecha_ars_real` en `PatrimonioMaximoOut` (schema + servicio + tipo TS) |
| 2.5 | Drawdown de 0% se reportaba como "datos insuficientes" | `diagnostico_engine.py`: `if dd_val` → `if dd_val is not None` |
| 2.6 | `get_progreso_objetivo` no validaba que el objetivo perteneciera a la cartera pedida | Filtro agregado: `ObjetivoInversion.cartera == cartera` |
| 2.7 | Grilla de sensibilidad con pasos irregulares (saltaba `base±s`) | `Objetivo.tsx`: grilla ahora `[base-2s, base-s, base, base+s, base+2s]` |
| 2.8 | `calcularDesde`: `toISOString()` en UTC + `setMonth(-1)` desbordaba en días 31 | `utils.ts`: formateo en fecha local + `restarMeses` clampea al último día del mes destino |

Verificación: `_convertir(100, USD, ARS)` con MEP=1000 → `100000.0`; `get_resumen`
devuelve `valor_actual_ars = 2200000.0` donde antes daba `0.0`. Suite completa:
143 pasan / 5 fallan (preexistentes, ver §4). Frontend: `tsc && vite build` sin errores.

---

## ✅ 3. Performance y limpieza (2026-08-27)

Medido sobre un dataset sintético de 1850 movimientos / 7825 precios / 25 tickers:
`get_diagnostico` pasó de **2024ms a 835ms** (-59%). Commit `76600c6`.

| Ítem | Fix aplicado |
|------|--------------|
| `_precio_conocido` O(n) por lookup | `bisect` con `key=`, sin materializar la lista de fechas |
| Los 8 analytics del diagnóstico recargaban la tabla de precios entera | `_precios_por_ticker` cacheado en `db.info` (vive una request), con listener `after_commit`/`after_flush` que lo invalida ante cualquier escritura |
| `get_diagnostico` recalculaba `get_resumen` ×3 y `get_rendimiento_por_ticker` ×2 | Se calculan una vez y se pasan por parámetro opcional a `get_aportes_historicos`, `get_progreso_objetivo` y `get_vencimientos` |
| `get_evolucion` re-deflactaba todo el histórico por punto (O(n·m)) | Acumulación incremental: el factor `CER_hoy/CER_i` es fijo por movimiento |
| `Objetivo.tsx` corría `resolverFechaAlcanzable` ×3 (1200 meses c/u) en el render | `useMemo` |
| `datetime.utcnow()` deprecado | `datetime.now(UTC)` |
| Import muerto de `riesgo_analytics` | Eliminado |
| `cotizaciones.py` era código muerto y bloqueaba el arranque 10s tras el proxy | Módulo borrado, junto al fallback `_mep_venta` inalcanzable y `httpx` de requirements |
| `_aplicar_solo_aportes` descartaba las ventas sin explicar por qué | Documentado: el modo corrige la cartera sólo con dinero nuevo |

---

## ✅ 4. Tests rotos preexistentes (2026-08-27)

Los 5 están corregidos (commit `ae917f2`). En 4 de los 5 el test estaba mal, no el código:

| Test | Diagnóstico |
|------|-------------|
| `test_risk_engine::test_beta_calculo_manual` | Faltaba `import statistics` en el test |
| `test_health_score::test_health_score_mezcla` | El tope por críticos (59) es un techo, no un piso: con score 55 no aplica |
| `test_escenario_engine::test_resolver_preset_personalizado_vacio` | `resolver_preset` inyecta `horizonte_meses: 120` a propósito |
| `test_validation_reglas::test_instrumentos_ticker_duplicado` | El fixture dejaba campos vacíos que emiten sus propias advertencias |
| `test_validation_reglas::test_precios_precio_cero` | Decisión de negocio: se mantiene el rechazo (un 0 en el Sheet es casi siempre una celda vacía mal parseada) y se documenta |

---

## ✅ A. Bugs de cálculo de la segunda revisión (2026-08-27)

Commit `b57231b`. Cubiertos por `backend/tests/test_bugs_calculo.py` (15 tests).

| # | Bug | Fix aplicado |
|---|-----|--------------|
| A1 | Rendimiento por ticker: `inversion_total_*` sólo sumaba compras, así que una posición vendida o amortizada a medias comparaba el valor del remanente contra el capital entero (≈ -40% falso) | `_recorrer_movs_ticker` extraído de `get_pnl_realizado_no_realizado`: ambas funciones comparten la convención de costo remanente. El rendimiento incluye además los ingresos cobrados |
| A2 | `get_aportes_historicos` contaba los dividendos como aporte de capital; si se reinvertían, el mismo peso se sumaba dos veces e inflaba toda la proyección de Objetivo | Los ingresos no alteran el aporte neto |
| A3 | El precio promedio deflactado por CER usaba el CER de la primera compra para todas | Cada compra se ajusta con el CER de su fecha, ponderado por cantidad; `None` si falta algún CER |
| A4 | Un bono sin precio cargado desaparecía de Vencimientos, siendo que su vencimiento no depende del precio | La lista se arma desde las tenencias; `valor_actual_*` queda en `None` si no hay con qué valuar |
| A5 | Con un único movimiento hecho hoy, los boundaries quedaban `[hoy, hoy]` → TWR espurio de casi -100% | Un solo boundary devuelve `None`. Las tres variantes de TWR se unificaron en `_calcular_twr_encadenado` |
| A6 | Una posición sin conversión a ARS se contaba con `valor_ars=0` pero seguía sumando en USD, hundiendo los totales en pesos de Exposición y Rebalanceo | Se descarta, igual que en USD |
| A7 | El sync reemplazaba las carteras conocidas en vez de unirlas al fallback de la DB: podía borrar objetivos y rebalanceo de una cartera válida | Unión con `carteras_fallback` |

---

## ✅ B-D. Consistencia de UI y mejoras funcionales (2026-08-27)

Commits `0de4ce3` y `124b0c6`.

| # | Tema | Fix aplicado |
|---|------|--------------|
| B1 | El botón de sync está en todas las pantallas, pero sólo `useInversiones` refetcheaba: Riesgo, Patrimonio, Diagnóstico, Comisiones y Precios seguían mostrando datos previos al sync | `syncVersion` en el contexto, sumado a las deps de los ~30 `useEffect` que traen datos (incluidos `useBenchmarkSeleccionado` y `useObjetivoInversion`) |
| B2 | El `value` del provider se recreaba en cada render y re-renderizaba a los 21 consumidores | `useMemo` en el provider + objeto estable desde `useInversiones` |
| D1 | Posiciones exportaba CSV con `join(',')` sin escapar (un nombre con coma corría las columnas) y sin BOM | `utils/csv.ts` con escape, `;` y BOM UTF-8; botones nuevos en Movimientos y Comisiones |
| D2 | La cartera y la moneda se reiniciaban en cada carga | `localStorage` con `try/catch`; si la cartera guardada ya no existe, vuelve al consolidado |
| D3 | Con el toggle en ARS, los gráficos de comisiones por mes y año seguían en USD sin avisar | El backend devuelve `total_ars` para esos períodos y el gráfico respeta el toggle |
| D4 | Volver a la app tras unos segundos te sacaba de la pantalla y te mandaba al Resumen | Sólo si estuviste ausente 5 minutos o más |

---

## Verificación end-to-end (2026-08-27)

Con la app levantada (`docker compose -f docker-compose.yml -f docker-compose.corporate.yml up`)
y un sync real contra el Sheet (health score 100, 12 movimientos / 7 instrumentos / 35 precios):

- Los 19 endpoints de `/consolidado/*` y los de las 3 carteras responden 200.
- Un segundo sync consecutivo preserva carteras, objetivos y rebalanceo (A7).
- `aportado_a_la_fecha_usd` del objetivo coincide con el `valor_invertido_usd` de la posición
  (consistencia A1 ↔ A2).
- El frontend se sirve y el bundle incluye los cambios.
