# Plan de corrección de bugs — pendientes

Origen: revisión estática completa de backend + frontend (2026-08-26).
Los 3 bugs críticos ya están corregidos y verificados; acá queda lo que falta.

## Cómo correr las cosas

```bash
# Build (ambiente corporativo, con proxy)
docker compose -f docker-compose.yml -f docker-compose.corporate.yml build backend

# Tests: importan `backend.app.*`, así que necesitan la RAÍZ del repo como workdir.
# No sirve `docker compose run backend pytest` (ahí la app está en /app/app).
docker run --rm -v $(pwd):/repo -w /repo -e PYTHONPATH=/repo \
  inversiones-app-backend python -m pytest backend/tests/ -q
```

**Baseline actual: 139 pasan, 7 fallan.** Los 7 fallos son preexistentes (ver §4);
cualquier cambio nuevo no debería mover ese número hacia arriba.

---

## ✅ Ya corregido y verificado

| # | Bug | Archivo |
|---|-----|---------|
| 1 | `_convertir` USD→ARS no devolvía nada (`None` siempre) → toda valuación en ARS de instrumentos USD daba 0 | `backend/app/services/inversiones_analytics.py:47-52` |
| 2 | Crash 500 en Performance Relativa: los `None` de `_calcular_twr_mensual` llegaban a `calcular_beta`/`calcular_tracking_error` | `backend/app/services/benchmarks_analytics.py:190-217` |
| 3 | El sync borraba `IndiceMercado` incondicionalmente, perdiendo el histórico CER/MEP cuando Movimientos o Precios estaban bloqueadas | `backend/app/services/inversiones_sync.py:186-196, 313-317` |

Verificación: `_convertir(100, USD, ARS)` con MEP=1000 → `100000.0`; `get_resumen`
devuelve `valor_actual_ars = 2200000.0` donde antes daba `0.0`.

---

## 1. Prioridad alta

### 1.1 El gráfico del Comparador siempre viene vacío ⚠️ NUEVO
`backend/app/services/benchmarks_analytics.py:344-363`

`construir_indice` devuelve fechas de **fin de mes** (`_ultimo_dia_mes`), pero la serie
se arma comparando contra `date(anio, mes, 1)`. La igualdad `f == punto["fecha"]` nunca
matchea → `punto["cartera"]` y todas las fuentes salen `None`. Verificado: 0 coincidencias.

**Fix**: normalizar a fin de mes al construir `punto["fecha"]`, o indexar los índices por
`(anio, mes)` en vez de por `date`. Ojo que `periodo_desde/hasta` sí usan día 1 y el
schema los expone así — mantener esa parte.

### 1.2 Benchmarks "Dólar (MEP)" / "Inflación (CER)" / ticker no funcionan en 3 de 4 pantallas
`riesgo_analytics.py:79`, `benchmarks_analytics.py:165`, `ticker_analytics.py:250`

`get_benchmarks_disponibles` los ofrece en el dropdown, pero solo `get_performance_compare`
los resuelve vía `_resolver_fuente`. Las otras tres llaman `_benchmark_retornos_mensuales`
directo (solo mira la tabla `BenchmarkValor`) → `{}` → "sin benchmark" silencioso.

**Fix**: reemplazar las 3 llamadas por `_resolver_fuente`. Cuidado con el import circular
(`riesgo_analytics` ya importa dentro de la función por eso).

### 1.3 `exceso_retorno` y `tracking_error` son el mismo número
`benchmarks_analytics.py:243,246`

Ambos campos reciben el mismo objeto. El valor real es el tracking error (desvío del
exceso); el exceso de retorno debería ser la **media** del exceso, anualizada.

**Fix**: agregar `calcular_exceso_retorno_medio` en `risk_engine` y usarlo para
`exceso_retorno`, dejando `tracking_error` como está.

### 1.4 La comisión anualizada se infla varias veces
`diagnostico_engine.py:265-270`

Toma las últimas 12 *entradas* de `por_mes` y anualiza con `12 / meses_cubiertos`, pero
`get_comisiones` **omite los meses sin comisión** (`inversiones_analytics.py:2023`). Con 2
meses operados en el año, multiplica ×6 → falsos "Comisión elevada" críticos. Además con
historial viejo toma meses de hace años como si fueran actuales.

**Fix**: calcular la ventana por **fecha** (últimos 12 meses calendario desde hoy) y usar
`meses_cubiertos = 12` fijo, tratando los meses ausentes como 0.

### 1.5 Las amortizaciones rompen la identidad `resumen` ↔ `pnl-realizado`
`inversiones_analytics.py:480-482` (el `if ...: pass` que no hace nada)

`get_resumen` no descuenta la amortización de `total_invertido`, pero
`get_pnl_realizado_no_realizado` sí la trata como venta (línea ~1636). Los dos endpoints
difieren exactamente en Σ(amortizaciones), contradiciendo el docstring de la línea ~1578.
Peor: `_flujos_cashflow` **sí** cuenta la amortización para el XIRR, así que
`rendimiento_simple` y `xirr` se contradicen dentro del mismo `get_resumen`.

**Fix**: decidir la convención (recomendado: amortización = devolución de capital, o sea
igual que venta) y aplicarla en los 3 lugares. Agregar un test de la identidad.

### 1.6 Un ticker sin precio actual borra también su P&L realizado
`inversiones_analytics.py:1666-1667`

El `continue` descarta el ticker entero, perdiendo `realizado_usd` e `ingresos_usd` ya
calculados, que no necesitan precio actual.

**Fix**: emitir la fila con `no_realizado_* = None` en vez de saltear el ticker.

---

## 2. Prioridad media

| # | Bug | Archivo | Fix |
|---|-----|---------|-----|
| 2.1 | Spinner infinito si el backend no responde: `fetchCarteras` sin `try/catch`, `loading` queda en `true` y `error` nunca se setea | `frontend/src/hooks/useInversiones.ts:32-36,61-63` | envolver en try/catch y setear `error` |
| 2.2 | Race condition al cambiar de cartera: respuestas fuera de orden pisan datos | `frontend/src/hooks/useInversiones.ts:38-59` | `AbortController` o guard de secuencia |
| 2.3 | `otros_ajustes` hardcodeado en 0 pese al docstring que promete comisiones; imports muertos (`_monto_bruto`, `_comision_usd`, `_comision_ars`, `_to_usd`, `_convertir`) | `patrimonio_analytics.py:177-179` | implementarlo o corregir docstring + borrar imports |
| 2.4 | La fecha del máximo patrimonial siempre es la de USD; `fecha_maximo_ars` y `_ars_real` se calculan y nunca se usan | `patrimonio_analytics.py:245-254,337` | exponer las 3 fechas |
| 2.5 | Drawdown de 0% se reporta como "datos insuficientes" (`if dd_val` en vez de `is not None`) | `diagnostico_engine.py:314-315` | usar `is not None` |
| 2.6 | `get_progreso_objetivo` no valida que el objetivo pertenezca a la cartera pedida | `inversiones_analytics.py:2146` | filtrar también por `cartera` |
| 2.7 | Grilla de sensibilidad con pasos irregulares: da `[base-3s, base-2s, base, base+2s, base+3s]`, saltea `base±s`. Primera expresión tiene un `cons - cons + cons` muerto | `frontend/src/pages/Objetivo.tsx:133-139` | usar `[base-2s, base-s, base, base+s, base+2s]` |
| 2.8 | `calcularDesde`: `toISOString()` convierte a UTC (en UTC-3 después de las 21hs da el día siguiente) y `setMonth(-1)` desde un día 31 desborda (31/3 → 3/3) | `frontend/src/utils.ts:72-83` | formatear en local y clampear el día |

---

## 3. Prioridad baja / performance

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

## 4. Tests rotos preexistentes (7)

Ninguno tiene que ver con los fixes ya aplicados — el baseline fallaba igual antes.

| Test | Causa |
|------|-------|
| `test_patrimonio_analytics.py::test_patrimonio_history_single_buy` | fixture no setea `nombre` (NOT NULL) → `IntegrityError` |
| `test_patrimonio_analytics.py::test_patrimonio_decomposition_identity` | ídem |
| `test_risk_engine.py::test_beta_calculo_manual` | `NameError` |
| `test_escenario_engine.py::test_resolver_preset_personalizado_vacio` | — |
| `test_health_score.py::test_health_score_mezcla` | assert |
| `test_validation_reglas.py::test_instrumentos_ticker_duplicado` | assert |
| `test_validation_reglas.py::test_precios_precio_cero` | espera que precio 0 sea válido, la regla lo rechaza |

**Arreglar primero los dos de patrimonio**: `test_patrimonio_decomposition_identity` es
justamente el test que habría cazado el bug de `_convertir`, y lleva roto desde siempre
fallando en el setup del fixture. Es el que da cobertura real a lo que se corrigió.

---

## Orden sugerido de ejecución

1. Arreglar los fixtures de `test_patrimonio_analytics` (§4) → da red de seguridad.
2. §1.1 Comparador (bug visible, fix chico).
3. §1.2 benchmarks virtuales (afecta 3 pantallas).
4. §1.5 convención de amortización (toca varios cálculos, conviene con tests verdes).
5. §1.3, §1.4, §1.6.
6. §2 completo.
7. §3 según aparezca dolor real de performance.
