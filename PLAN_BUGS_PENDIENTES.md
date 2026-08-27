# Plan de corrección de bugs — pendientes

Origen: revisión estática completa de backend + frontend (2026-08-26).
Los bugs críticos, de prioridad alta y de prioridad media ya están corregidos y
verificados (2026-08-27); acá queda solo §3 (baja prioridad / performance).

## Cómo correr las cosas

```bash
# Build (ambiente corporativo, con proxy)
docker compose -f docker-compose.yml -f docker-compose.corporate.yml build backend

# Tests: importan `backend.app.*`, así que necesitan la RAÍZ del repo como workdir.
# No sirve `docker compose run backend pytest` (ahí la app está en /app/app).
docker run --rm -v $(pwd):/repo -w /repo -e PYTHONPATH=/repo \
  inversiones-app-backend python -m pytest backend/tests/ -q
```

**Baseline actual: 143 pasan, 5 fallan.** Los 5 fallos son preexistentes (ver §4);
cualquier cambio nuevo no debería mover ese número hacia arriba.

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

## 3. Prioridad baja / performance (pendiente)

- `_precio_conocido` reconstruye la lista de fechas en **cada** llamada (O(n) por lookup),
  dentro de bucles anidados boundaries × tickers — `inversiones_analytics.py:264-266`.
  Cachear las fechas junto a `precios_por_ticker`.
- `get_diagnostico` invoca 8 analytics que recargan cada una la tabla completa de precios y
  movimientos; `get_vencimientos` vuelve a llamar `get_rendimiento_por_ticker` y
  `get_progreso_objetivo` vuelve a `get_resumen`. Pasar un contexto compartido.
- `get_evolucion` recalcula el CER de *todos* los movimientos acumulados en cada punto del
  gráfico, O(n·m) — `inversiones_analytics.py:1832-1839`. Acumular incrementalmente.
- `Objetivo.tsx:391`: `resolverFechaAlcanzable` (hasta 1200 meses simulados ×3) corre en el
  render sin `useMemo`.
- `datetime.utcnow()` deprecado (ya emite `DeprecationWarning` en los tests) —
  `inversiones_sync.py:59`. Usar `datetime.now(datetime.UTC)`.
- Import muerto de `riesgo_analytics` en `benchmarks_analytics.py:92`.
- `cotizaciones.get_rates_for_date` devuelve `{}` siempre → el fallback de MEP en
  `_mep_sheet` es código muerto. Implementarlo o borrarlo junto con `_mep_venta`.
- `_aplicar_solo_aportes` descarta silenciosamente los ítems con `accion == "vender"`
  (`rebalanceo_engine.py:270`). Confirmar si es intencional; si lo es, documentarlo.

---

## 4. Tests rotos preexistentes (5)

Ninguno tiene que ver con los fixes ya aplicados — el baseline fallaba igual antes.
(Los 2 de `test_patrimonio_analytics` y los 2 de `evaluar_comisiones` que estaban acá
ya se corrigieron como parte de §4-original, §1.4 y su cobertura de test.)

| Test | Causa |
|------|-------|
| `test_risk_engine.py::test_beta_calculo_manual` | `NameError` (falta `import statistics` en el test) |
| `test_escenario_engine.py::test_resolver_preset_personalizado_vacio` | — |
| `test_health_score.py::test_health_score_mezcla` | assert |
| `test_validation_reglas.py::test_instrumentos_ticker_duplicado` | assert |
| `test_validation_reglas.py::test_precios_precio_cero` | espera que precio 0 sea válido, la regla lo rechaza |

---

## Orden sugerido de ejecución (restante)

1. §3 según aparezca dolor real de performance.
2. Opcional: arreglar los 5 tests rotos preexistentes de §4 (ninguno es bloqueante).
