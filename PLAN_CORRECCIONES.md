# Plan de correcciones — hallazgos de la revisión de Olas 3-5

Revisión de código (2026-08-28) sobre los ítems marcados como ✅ en
`PLAN_MEJORAS_PENDIENTES.md` (Ola 3 ítems 1/1b/2/3, Ola 4 ítem 4, Ola 5 ítems 5-11).
Baseline al momento de la revisión: **298 tests pasan, 0 fallan**.

Cada hallazgo tiene un ID (`A`=alto, `M`=medio, `B`=bajo) que se usa en los commits y en los
tests nuevos, para poder rastrear qué quedó cerrado.

**Orden de las etapas**: primero lo que corrompe datos ya guardados (cada sync que pasa
acumula más filas malas), después lo aislado y barato, después el realismo de la inferencia de
renta fija, y al final performance y UX. Las etapas 2 a 6 son independientes entre sí; la 1 es
la única que conviene hacer antes que el resto.

**Regla de trabajo** (igual que el resto del proyecto):
- Todo corre en Docker. Tests:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.corporate.yml run --rm \
    -v $(pwd):/repo -w /repo -e PYTHONPATH=/repo \
    backend python -m pytest backend/tests/ -q
  ```
  (sin proxy: `docker compose run --rm ...` con los mismos flags)
- Build de frontend (verifica TypeScript): `docker compose build frontend`
- Un commit por etapa, con los IDs de hallazgo en el mensaje.
- Los tests de `market_data`/sync **siempre mockean** el fetch; nunca red real
  (`backend/tests/conftest.py` fuerza `USE_EXTERNAL_APIS=false`).

---

## Etapa 1 — Integridad de la serie de precios automática

**Por qué primero**: `precios_instrumento` alimenta toda valuación (resumen, riesgo, P&L,
vencimientos, diagnóstico). Los cuatro hallazgos de acá o guardan datos incorrectos o dejan de
guardar los correctos, y el daño se acumula sync a sync.

### A4 — Filas `api` que el Sheet pisó nunca se borran
`backend/app/services/inversiones_sync.py:399-415`

`claves_sheet` sólo evita **insertar**; una fila `api` guardada para `(TICKER, fecha)` que el
Sheet después empieza a cubrir queda conviviendo con la fila `sheet`. `_precios_por_ticker`
([inversiones_analytics.py:278](backend/app/services/inversiones_analytics.py#L278)) no
deduplica y `_precio_conocido` se queda con el último del grupo de igual fecha, en orden no
determinístico → el precio manual puede perder contra el automático.

**Fix**: en el bloque de purga, agregar el borrado de filas `fuente=='api'` cuyas
`(ticker, fecha)` estén en `claves_sheet`. Como el Sheet se reescribe entero en cada sync, esto
además limpia de una vez las filas ya duplicadas en la DB del usuario (no hace falta migración).

**Tests** (`test_inversiones_sync_market_data.py`): sync con una fila `api` preexistente para
una fecha que el Sheet ahora trae → queda una sola fila y es la `sheet`.

### A2 — La moneda de la fila `api` sale de `Instrumentos`, no de la fila calibrada
`backend/app/services/market_data/precios.py:159` y `:294`

El número está calibrado contra `precios_sheet[...]["precio"]`, que tiene su propia columna
`Moneda` ([reglas_precios.py:93](backend/app/services/validation/reglas_precios.py#L93)), pero
se persiste con `inst.get("moneda")`. Si difieren, se guarda un valor en la escala de una
moneda etiquetado con otra (~1300x de error, mezclado en la misma serie que las filas `sheet`).

**Fix**: `ultimo_sheet` ya guarda `(fecha, precio)` por ticker → pasar a
`(fecha, precio, moneda)` y usar esa moneda al construir la fila. Aplica a las dos rutas
(`_fetch_precios_live_api` y `fetch_backfill_renta_fija_api`). Si la moneda del Sheet difiere de
`inst.moneda`, emitir un `SyncIssue` INFO (es un dato que el usuario querría revisar).

**Tests** (`test_market_data_precios.py`): instrumento declarado `USD` con serie de Precios en
`ARS` → la fila generada sale en `ARS`.

### A1 — La calibración de escala envejece y termina rechazando precios buenos
`backend/app/services/market_data/precios.py:130-153`

Se compara el precio de **hoy** contra el último precio manual, que puede tener meses (y va a
tenerlos, justamente porque la API reemplazó la carga manual). Entre `2.5` y `40` hay una zona
muerta: un bono en ARS que subió 3x desde la última carga manual cae ahí, se rechaza con
`escala_desconocida` (ADVERTENCIA), y como el precio manual no se actualiza nunca más, el
rechazo es permanente y se repite en cada sync (baja el health score y aparece como regla
recurrente).

**Fix** (decisión de diseño de la etapa): persistir el factor una vez determinado, en vez de
recalcularlo contra una referencia que envejece. Tabla nueva chica en `database.py`:

```python
class EstadoMarketDataTicker(Base):
    __tablename__ = "estado_market_data_ticker"
    ticker = Column(String, primary_key=True)
    factor_escala = Column(Numeric(10, 6), nullable=True)   # 1.0 | 0.01
    factor_fecha = Column(Date, nullable=True)              # cuándo se calibró
    backfill_estado = Column(String, nullable=True)         # None | 'sin_serie' | 'completo'
    backfill_intento = Column(Date, nullable=True)
```
con el mismo patrón de `ALTER TABLE`/`create_all` en `init_db` que se usó para
`indices_mercado.riesgo_pais`.

Lógica: si hay `factor_escala` guardado se usa tal cual; si no, se calibra como hoy contra el
último precio manual **y se guarda**. La recalibración sólo se rehace si aparece un precio
manual más nuevo que `factor_fecha` (el usuario volvió a cargar a mano → es una referencia
fresca y vale la pena revalidar).

*Alternativa sin tabla*, si se prefiere no tocar el esquema: calibrar contra la última fila
`fuente='api'` del ticker (que ya está en la escala del Sheet) cuando exista, y caer al precio
manual sólo la primera vez. Es más simple pero arrastra el factor implícitamente en los datos y
no deja lugar donde poner A3.

**Tests**: factor guardado se reusa aunque el precio manual quede viejo; un precio manual nuevo
dispara recalibración; ratio en zona muerta sin factor previo sigue rechazando.

### A3 — El backfill nunca converge para los tickers sin serie y se come el cupo
`backend/app/services/market_data/precios.py:242-251`

Si `fetch_historico_bono` devuelve `None` (ONs corporativas) o `[]`, no se inserta ninguna fila
`api`, así que el ticker no entra en `api_existentes_por_ticker`, su `hueco` queda en `10**6` y
queda **primero en la cola en todos los syncs**. Con 15 ONs en cartera,
`_MAX_BACKFILL_POR_SYNC = 15` se agota en tickers que nunca van a traer nada y ningún soberano
se backfillea jamás. Lo mismo, más leve, con cualquier ticker cuya serie arranque después del
piso: nunca llega a `piso + _TOLERANCIA_PISO_DIAS` y se re-pide para siempre.

**Fix**: usar `backfill_estado`/`backfill_intento` de la tabla de A1.
- `None` de `fetch_historico_bono` → `backfill_estado='sin_serie'`; esos tickers se saltean y
  no consumen cupo. Reintento sólo si `backfill_intento` tiene más de ~90 días (por si la fuente
  empieza a cubrirlos).
- Serie que llegó completa pero arranca después del piso → `backfill_estado='completo'` cuando
  la fecha más vieja devuelta por la API no mejora respecto de la corrida anterior (convergencia
  por "ya no baja más", no por distancia al piso).
- El `SyncIssue` info `sin_historico_backfill` se emite **una vez** al detectarlo, no en cada
  sync (hoy ensucia "reglas recurrentes").

**Tests**: dos corridas seguidas con un ticker que devuelve `None` → la segunda no vuelve a
pedirlo y el cupo queda libre para otro; ticker cuya serie no baja más → se marca `completo`.

**Cierre de la etapa**: tests verdes + una corrida real con `USE_EXTERNAL_APIS=true` revisando
la pestaña "Precios (API)" de Calidad de datos (debería quedar mucho más silenciosa).

---

## Etapa 2 — Correcciones puntuales, aisladas y baratas

Todas son cambios chicos, sin dependencias entre sí. Se pueden hacer en un solo commit.

### M7 — `necesidad` no se recalcula tras recortar por banda
`backend/app/services/rebalanceo_engine.py:308-317`

`_aplicar_banda_pesos` recalcula importe/acción/delta/comisión pero deja `necesidad` como
venía: una posición "mantener sin objetivo" recortada por el techo pasa a `delta_pp = -15` y
sigue rotulada `opcional`.

**Fix**: pasar `tolerancia_pp` a `_aplicar_banda_pesos` y recalcular
`necesidad=_necesidad_desde_delta(delta_nuevo, tolerancia_pp)` en el `replace(...)`.

**Extra (M7b)**: los ítems `tipo == "categoria_sin_instrumento"` se saltean el recorte
(`it.tipo != "ticker"` los deja pasar), así que una categoría con objetivo 40% y techo 20%
propone comprar 40%. Aplicarles el techo también, o dejarlo documentado en el docstring como
decisión explícita.

**Tests**: +2 en `test_rebalanceo_banda_pesos.py`.

### M8 — El bucket "Sin país" cuenta como categoría real
`backend/app/services/diagnostico_engine.py:341-356`

El guardrail pide `n_componentes >= 2`, pero `n_componentes` incluye el bucket "Sin país" que
agrega `_agrupar_sobre_total`
([contribucion_analytics.py:190-195](backend/app/services/contribucion_analytics.py#L190-L195)).
Una cartera con **un** país etiquetado y el resto sin etiquetar pasa el filtro, y el HHI trata
"Sin país" como si fuera otro país → subestima la concentración.

**Fix**: que `get_concentracion` devuelva `n_componentes_reales` (o `n_sin_clasificar`) en los
ejes que usan bucket residual — Sector y País — y que `score_diversificacion` filtre por eso.
De paso, el `detalle` no debería decir "(tipo, sector, mercado, país)" cuando el país no se
contó: armarlo con los ejes efectivamente usados.

**Tests**: +2 en `test_diagnostico_engine.py` (1 país real + resto sin etiquetar → País no
cuenta), +1 en `test_concentracion_pais.py`.

### M11b — La comisión se pierde si el movimiento no convierte a USD
`backend/app/services/inversiones_analytics.py:1873-1886`

En `get_vista_fiscal_por_anio`, el `continue` por `monto_usd is None` está **antes** del bucket
de comisiones, así que un movimiento sin conversión a USD pierde también su comisión aunque la
comisión en ARS sí se hubiera podido calcular.

**Fix**: mover el bloque de comisiones arriba del `continue`, acumulando cada moneda por
separado (es la convención del resto del archivo: cada agregado se suma sólo cuando su
conversión existe).

**Tests**: +1 en `test_vista_fiscal_por_anio.py`.

### B12 — `mensaje_muestra` y `total_syncs` en Calidad de datos
`backend/app/services/calidad_datos.py:80-83`

`tab`/`mensaje` sólo se actualizan si el issue es del último sync; para una regla que **no**
aparece en el último, el ejemplo queda el primero que devuelva la query (el más viejo), no "el
sync más reciente en que apareció" como dice el plan.

**Fix**: ordenar `todos_issues` por `sync_run_id` ascendente y sobrescribir siempre
`tab`/`mensaje` → el último en ganar es el más reciente. Y renombrar `total_syncs` a
`syncs_en_ventana` (o dejar el nombre y corregir el texto de la UI, que hoy dice "de los últimos
N syncs" con N = min(20, syncs reales) — que es correcto, pero el nombre del campo engaña).

**Tests**: +1 en `test_calidad_datos_historial.py`.

### B16 — Vencidos dentro de "% de la cartera que vence por año"
`backend/app/services/flujo_caja_analytics.py:605-618`

`por_anio` recorre todos los `items`, incluidos los `vencido`, así que aparecen años pasados en
un resumen que se lee como proyección.

**Fix**: excluir `item.get("vencido")` del `por_anio` (los ítems siguen en `items`), o separarlos
en una clave `vencidos` aparte si se los quiere mostrar.

**Tests**: +1 en `test_vencimientos_enriquecido.py`.

---

## Etapa 3 — Realismo del cronograma inferido de renta fija

**Por qué después de la 1**: depende de precios confiables (A1/A2) para que la paridad y la TIR
tengan sentido.

### A6 — Las amortizaciones proyectadas no tienen tope de capital
`backend/app/services/flujo_caja_analytics.py:196-206`

`_grilla_hacia_atras` genera una amortización del mismo monto por unidad cada
`amort_periodicidad_meses` desde hoy hasta el vencimiento, sin verificar que el total
(histórico + proyectado) no exceda el par. Para un bono con período de gracia — la mayoría de
los soberanos argentinos amortizan sólo en los últimos años — inferir "trimestral" de dos pagos
y extenderlo a toda la vida restante sobre-proyecta el capital varias veces. Eso alimenta el
flujo de caja, la TIR y la duration: está marcado como "est.", pero el error puede ser de 3-5x,
no un margen.

**Fix**: acotar la cantidad de cuotas futuras a lo que queda de capital:
`n_max_fut = max(0, round(1 / amort_por_unidad) - n_hist)` (con `amort_por_unidad` expresado
sobre par = 1), y quedarse con las **últimas** `n_max_fut` fechas de la grilla (las amortizaciones
se concentran al final). Si `amort_por_unidad` no permite estimar el total (par desconocido, ver
M9), degradar a *bullet* explícito en vez de proyectar una serie infinita, y decirlo en `notas`.

**Tests**: +3 en `test_flujo_caja_analytics.py` (bono con gracia: 2 cuotas históricas del 10%
→ como máximo 8 futuras; caso degradado a bullet).

### M9 — La paridad asume par = 1 por unidad
`backend/app/services/flujo_caja_analytics.py:544-560`

Es exactamente la suposición que `precios.py` se niega a hacer (calibra por ratio porque no sabe
si el Sheet carga por 1 VN o por lámina de 100). Si el Sheet carga por 100 VN, el factor de
escala da 1.0 (correcto para la serie) y la paridad sale ~7000% en la UI.

**Fix**: derivar el par del mismo dato del que se infiere todo lo demás — la amortización por
unidad y el cupón por unidad están en la misma escala que el precio, así que
`par ≈ 1 / amort_por_unidad` cuando hay amortizaciones inferidas; sin eso, inferirlo del orden
de magnitud del precio (1 vs 100) y dejarlo explícito en la respuesta (`par_asumido`) para que
la UI lo muestre. Si no se puede determinar, **no mostrar paridad** en vez de mostrar un número
sin sentido.

**Tests**: +2 en `test_vencimientos_enriquecido.py` (Sheet en escala 100 → paridad ~0.7 o
`None`, nunca 70).

---

## Etapa 4 — Riesgo país por campo, no por fila

### A5 — El riesgo país se descarta en toda fecha que el Sheet cubre
`backend/app/services/market_data/indices.py:63-71`

`fechas_excluir` se aplica por igual a CER, MEP y `riesgo_pais`, pero el Sheet **nunca** aporta
riesgo país, y `IndiceMercado.fecha` es `unique=True`
([database.py:76](backend/app/database.py#L76)), así que no hay forma de tener las dos fuentes
en la misma fecha. Si el usuario mantiene `Tipos de Cambio` al día — el caso esperado — la serie
queda con agujeros justo en los días recientes y "Último registro" muestra un valor viejo.

**Fix**: la regla "el Sheet gana" tiene que ser **por campo**, no por fila. Dos caminos:

1. *(recomendado, sin cambio de esquema)* `fetch_indices_mercado_api` deja de excluir fechas
   para `riesgo_pais` y devuelve, para las fechas que el Sheet ya cubre, filas "sólo riesgo
   país"; `inversiones_sync` las mergea sobre la fila `sheet` existente en vez de insertarlas
   (update del campo `riesgo_pais` sobre la fila de esa fecha). La fila sigue siendo
   `fuente='sheet'` — el campo es de la API por construcción, ya está documentado así en el
   modelo.
2. Separar `riesgo_pais` a su propia tabla `indice_riesgo_pais(fecha, valor)`. Más limpio
   conceptualmente, pero es una tabla para un solo indicador y obliga a tocar
   `get_indices_mercado`, el schema y la UI.

**Tests**: +2 en `test_indices_mercado_macro.py` (fecha cubierta por el Sheet con CER/MEP →
igual queda con `riesgo_pais`; el CER/MEP del Sheet no se pisa).

---

## Etapa 5 — Performance

### M10 — El TWR bruto duplica el costo del TWR
`backend/app/services/inversiones_analytics.py:519-522` y `:543-546`

`_resumen_sobre_movs` pasó de 3 a 5 recorridos encadenados (boundaries × tickers × valuación), y
el diagnóstico llama a `get_resumen` tres veces → +6 pasadas completas. Es una regresión sobre
el trabajo de `76600c6` (diagnóstico 2.0s → 0.8s), y los dos valores nuevos se consumen
únicamente en dos filas de la tabla de Rendimiento.

**Fix** — en orden de preferencia:
1. Calcular el drag de comisiones sin un segundo TWR: en `_calcular_twr_encadenado`, acumular
   por sub-período la comisión convertida y devolver el TWR bruto como subproducto de la misma
   pasada (misma cadena, dos productos).
2. Si (1) resulta enredado: parámetro `incluir_bruto: bool = False` en `_resumen_sobre_movs`,
   activado sólo por el endpoint de resumen que alimenta la pantalla Rendimiento.

**Medición**: antes/después con `duration_ms` del endpoint de diagnóstico sobre la cartera real,
anotado en el commit. **Tests**: los 3 de `test_twr_costo_operar.py` tienen que seguir pasando
sin cambios (son la especificación del valor esperado).

---

## Etapa 6 — Frontend y deuda menor

### B13 — Eliminar escenario guardado sin confirmación
`frontend/src/pages/Simulador.tsx`

Acción irreversible a un click. **Fix**: confirmación inline (el botón pasa a "¿Eliminar?" y
requiere un segundo click, con timeout), coherente con el resto de la app.

### B14 — Overrides de variación por instrumento
`frontend/src/pages/Simulador.tsx`, `frontend/src/components/inversiones/EscenarioConfigPanel.tsx`

- El universo de tickers sale de `getRendimientoPorTicker`, que **descarta los tickers sin
  cotización** ([inversiones_analytics.py:1596](backend/app/services/inversiones_analytics.py#L1596)):
  una posición sin precio cargado no se puede override-ear. Tomar el universo de las tenencias
  (o unir ambas fuentes).
- `setTicker` hace `return` ante `Number.isNaN`, lo que hace frágil tipear un valor negativo en
  un `input type="number"` controlado. Mantener el texto crudo en estado local y sincronizar al
  blur / cuando parsea.

### B15 — Serie de inflación mensual
`backend/app/services/inversiones_analytics.py:2201-2215`

- No filtra por `fuente`: una fila manual en la pestaña Benchmarks llamada igual que
  `_BENCHMARK_INFLACION_INDEC` intercala niveles y ensucia las variaciones → filtrar
  `BenchmarkValor.fuente == 'api'`.
- Asume que dos filas consecutivas son meses consecutivos: si falta un mes, la variación de dos
  meses se muestra como si fuera de uno → verificar el salto y saltear (o marcar) el punto.
- El primer mes de la ventana siempre se pierde (necesita el nivel previo): traer un mes extra
  hacia atrás del filtro `fecha >= desde`.

**Tests**: +2 en `test_indices_mercado_macro.py`.

### M11a — La vista fiscal reimplementa `_recorrer_movs_ticker`
`backend/app/services/inversiones_analytics.py:1867-1912`

El docstring dice "misma convención (ver `_recorrer_movs_ticker`)" pero es una copia del bucle.
Hoy coinciden y hay un test de identidad que lo verifica, pero cualquier cambio en una sola de
las dos rompe la identidad en silencio.

**Fix**: extender `_recorrer_movs_ticker` con un callback opcional
`on_realizado(mov, monto_usd, monto_ars, costo_removido_usd, costo_removido_ars)` (y otro para
ingresos), y que la vista fiscal se cuelgue de ahí para bucketizar por año. Es refactor puro:
el test de identidad existente es la red de seguridad.

---

## Fuera de alcance de este plan

La sección "Higiene de datos detectada, todavía sin tocar" de `PLAN_MEJORAS_PENDIENTES.md`
(columna sin encabezado en `Precios`, `TipoCambio` muerto, `es_jubilacion` huérfana,
`glosario.ts` duplicado, `routers/objetivos_inversion.py` sin `_validar_cartera`, `README.md` y
`FUNCIONALIDADES.md` desactualizados) sigue vigente y no se toca acá.

`UMBRAL_APROXIMADO_DIAS = 45` sigue hasta que la renta fija **y** variable tengan cobertura
densa; la Etapa 1 es requisito para poder evaluarlo.
