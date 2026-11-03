# Ciclos de mercado (`/ciclos`)

Herramienta de análisis para entender, a largo plazo, qué sectores, industrias, commodities, regiones, países, activos y temas
ganan o pierden fuerza frente a una referencia, y cómo se cruza eso con la cartera. **Describe lo que ya ocurrió: no genera
recomendaciones de compra o venta**, no combina las dimensiones en un puntaje único y no afirma causalidad.

## Qué hay

| Pestaña | Qué muestra |
|---|---|
| **Panorama** | Régimen macro (hoy «no disponible»), mapa de rotación relativa con trayectorias, cambios de liderazgo confirmados, mapa de calor de rendimientos |
| **Sectores y activos** | Sectores, industrias, commodities (separados), activos y temas, cada uno con su estado y rendimiento |
| **Regiones** | Regiones y países, comparaciones habituales (EE.UU. vs. Europa, China vs. India...) y ficha de país |
| **Relaciones** | Matriz de correlaciones, comparación histórica sobre un mismo período, adelantos y rezagos |
| **Mi cartera** | Capital por estado del ciclo, instrumentos de un grupo, simulador de rotación |
| **Ficha** (`/ciclos/grupo/:id`) | Base 100 contra la referencia, métricas por separado, historial de rotación, período histórico a elegir, tus posiciones en el grupo |

## Arquitectura

```
catalogos/ciclos_grupos.json     qué se mide (grupos, proxies, referencias, reglas de cartera, comparaciones)
catalogos/ciclos_periodos.json   períodos históricos (sólo fechas)
services/ciclos_catalogo.py      carga y valida el catálogo
services/ciclos_ingesta.py       descarga de Yahoo -> serie_ohlcv (clave SIMBOLO@BENCH) + cobertura
services/ciclos_engine.py        motor PURO: rotación, rendimientos, riesgo, correlaciones, país
services/ciclos_analytics.py     adaptador DB: panorama, detalle, relaciones, país
services/ciclos_cartera.py       cruce con la cartera y simulador
services/ciclos_regimen.py       régimen macro (estructura, sin datos)
services/ciclos_senales_engine.py + ciclos_historial.py   cambios confirmados sobre una foto semanal (etapa 2)
routers/ciclos.py                API
```

Reutiliza, sin duplicarlo: `indicadores_engine.ema/sma`, `risk_engine.calcular_drawdown`,
`contribucion_engine.calcular_correlacion_par`, `correlaciones_engine.construir_matriz` (y la tabla de calor de
`/correlaciones`), `inversiones_analytics._clasificados_valorizados/_agrupar` (el criterio único de totales de Exposición),
`clasificacion_analytics` (clasificación y emisor único), `impacto_cartera_engine.comparar_eje`, `simulador_decision`
(umbrales de Salud y distancia a objetivos), `benchmarks.py` (almacén `SIMBOLO@BENCH` en `serie_ohlcv`).

## Datos

### Fuente y almacenamiento
Cierres diarios de **Yahoo Finance con `auto_adjust=True`** (ajustados por dividendos y splits: para un ETF es retorno total).
Se guardan en `serie_ohlcv` bajo `SIMBOLO@BENCH`: esa clave ya está protegida de la purga de huérfanas del sync y no es del
universo técnico. No se creó otra tabla de precios. No se usa IOL (no gasta cupo).

### Ingesta (`ciclos_ingesta`)
- **Primera vez:** historia completa desde 2005-01-01 (la serie empieza cuando empieza en Yahoo; nunca se extrapola hacia atrás).
- **Después:** incremental con 7 días de solape. Sólo ruedas cerradas (`fecha < hoy`).
- **Reajuste:** un dividendo o split reescribe toda la historia ajustada. Si algún cierre del solape difiere más de 0,02 % de lo guardado,
  se vuelve a bajar el símbolo completo y se **reemplaza** (una sola escala por serie). Mezclar escalas rompería todo cociente.
- La red va fuera de `sync_lock`; la escritura, en un commit con el lock. Corta ante un 429 y guarda lo ya obtenido.
- Tabla `ciclos_proxy_estado`: cobertura real por símbolo (`ok`, `no_encontrado`, `error`, primera/última fecha, barras, reajustes).
  Un grupo cuyo proxy no se pudo bajar se muestra como «sin datos (motivo)» y **nunca se calcula con lo que haya**.
- Tabla `ciclos_estado_historial`: foto semanal del estado (ver «Señales»). No es fuente de verdad.
- Job `ciclos` (lunes a viernes 19:00, `CICLOS_HORAS`/`CICLOS_MINUTO`; vacío lo desactiva; requiere `SCHEDULER_ENABLED`).
  A mano: `POST /api/inversiones/ciclos/refrescar`.

### Cobertura real (verificada contra Yahoo, 2026-11-03)
66 símbolos con datos. Desde 2005 la mayoría. Historias más cortas: XLC y AIQ (2018), ETH-USD (2017), XLRE (2015), BTC-USD (2014),
INDA (2012), MCHI y ARGT (2011), CPER (2011), SOYB y WEAT (2011), CORN (2010), AAXJ y ACWI (2008), ICLN (2008).
Hallazgos que condicionan el análisis:
- Los pares FX de Yahoo tienen **huecos de hasta 26 días** (BRL=X, HKD=X, INR=X): el efecto cambiario queda «sin dato» si el hueco cae cerca de las fechas.
- `^MERV` llegó con ~17 días de atraso: se marca como desactualizado y el índice local de Argentina queda «sin dato».
- Aluminio (`ALI=F`): contrato continuo con huecos de hasta 27 días y saltos de roll → **inactivo** (queda cubierto por Metales industriales, DBB).
- 5 y 10 años sólo aparecen en el mapa de calor si algún grupo tiene esa historia.

## Fórmulas

**Rotación relativa** (inspirada en los Relative Rotation Graphs; **no** es la metodología propietaria JdK), con ventana `n = 13` semanas:

```
RS          = P_grupo / P_benchmark
RS_Ratio    = 100 · RS / EMA(RS, n)
RS_Momentum = 100 · RS_Ratio / EMA(RS_Ratio, n)
```
La EMA se siembra con la SMA de las primeras `n` observaciones (`indicadores_engine.ema`). 100 es el punto neutral de los dos ejes.

| Cuadrante | RS-Ratio | RS-Momentum |
|---|---|---|
| Leading | ≥ 100 | ≥ 100 |
| Weakening | ≥ 100 | < 100 |
| Lagging | < 100 | < 100 |
| Improving | < 100 | ≥ 100 |

Un empate exacto en 100 se resuelve del lado «≥» (se redondea a 9 decimales para que no dependa del error de punto flotante).

**Alineación y calidad**
- Se **intersectan** las fechas del grupo y del benchmark (Bitcoin y un ETF se comparan los días hábiles de ambos). La barra semanal es el
  último día común de la semana ISO.
- Una semana sin ninguna fecha común es un **hueco**: la EMA no lo cruza; se usa el último tramo continuo y se informa cuántas semanas se descartaron.
- Mínimo `2n + cola` semanas continuas (34 con los valores por defecto): menos → `datos_insuficientes`.
- Último dato en común más de 10 días atrás → `desactualizado`: no se dibuja ningún punto «actual» (la historia sigue disponible como historia).
- **Cambio confirmado:** el nuevo cuadrante se sostiene 3 semanas seguidas. Un tramo más corto es transitorio y no interrumpe el cuadrante confirmado; el último, si es corto y distinto, queda «pendiente».
- Un empate o una ventaja **constante** hace que el momentum tienda a 100 (por la propia fórmula): una ventaja estable no se queda indefinidamente en Leading. Es una propiedad del método, no un error.

**Rendimientos:** cierre en o antes de la fecha objetivo (tolerancia 6 días) en las dos puntas. Si la serie empieza después → «sin datos suficientes»; no se acorta el período.
Relativo = `(1 + r_grupo) / (1 + r_benchmark) − 1` sobre las mismas dos fechas. Anualizado desde 1 año: `(1 + r)^(365/días) − 1`.

**Riesgo:** volatilidad = desvío de los retornos semanales × √52 (mínimo 12 semanas); máxima caída por `risk_engine.calcular_drawdown` sobre la serie semanal,
con la recuperación en semanas. **Tendencia:** distancia a la SMA de 40 semanas y pendiente de esa media en 4 semanas.

**Correlaciones:** Pearson (`calcular_correlacion_par`) sobre retornos en dólares medidos sobre **una grilla común**: viernes con tolerancia de 3 días (semanal) o las ruedas del
S&P 500 (diaria). Un período con un extremo faltante no existe; no se encadena. Informa la cantidad de observaciones y el período efectivo. 3 meses usa frecuencia diaria por defecto.

**Desfases:** correlación entre el retorno semanal de `a` en la semana `t` y el de `b` en `t + k`, `k ∈ [−8, 8]`. Con 17 desfases es normal que alguno supere la banda `±1,96/√n` por azar:
se marca como hipótesis estadística, no como predicción.

**Descomposición de un país** (mismas dos fechas, tres medidas que **no** son equivalentes):
ETF en USD (incluye gastos y distribuciones) · índice local en su moneda (de precio) · efecto cambiario.
`índice local en USD = (1 + local)·(1 + efecto) − 1` y `diferencia del vehículo = ETF − índice local en USD`. Una pieza sin dato cercano queda `None` con su motivo.

**Sintético** (`sintetico.metodo = "equiponderado_semanal"`): índice base 100 que encadena el promedio simple de los retornos semanales de los miembros, **sólo en las semanas en que todos tienen dato**.
Una semana en que falta alguno no aparece (hueco). Hoy ningún grupo activo lo usa; el mecanismo está listo, validado y testeado.

### Moneda
La **rotación se calcula siempre en USD**: el tipo de cambio se cancela en el cociente grupo/benchmark, así que el cuadrante no cambia con la moneda. Rendimientos, riesgo y gráficos pasan a pesos con el
**MEP de cada fecha** (hasta 7 días hacia atrás); una fecha sin MEP se descarta, no se completa, y se avisa.

## Mi cartera

- Mismas posiciones, mismo total y mismos buckets residuales que **Exposición** (hay un test de equivalencia). Nada se descarta: lo que no tiene sector, país o región entra en «Sin sector/país/región».
- **Dimensiones excluyentes** (sector, región, país): cada una suma 100 % y reparte el capital por cuadrante. El mapeo categoría → grupo sale de `eje_cartera` en el catálogo.
- **Superpuestas** (industrias, commodities, temas): una empresa puede ser tecnología, semiconductores e inteligencia artificial. Se muestran aparte, **no se suman**; la «unión» de cada tipo cuenta cada posición una vez.
- Un grupo padre incluye a sus hijos (el oro también es un commodity).
- **Temas:** no hay clasificación de fuente externa ni holdings de ETFs. Cada tema es una regla sobre la clasificación existente más una **lista curada** de tickers, marcada como tal y con la regla visible. Es un criterio amplio y revisable.
- **Emisor único:** un CEDEAR, su variante en pesos/dólares y su acción de origen cuentan una vez (`Contexto.base`).
- **Simulador:** traslada un % del **total de la cartera** desde un grupo (reduciendo sus posiciones en proporción) hacia otro (una posición sintética con la clasificación que el catálogo afirma del destino; lo que no define queda en «Sin …»).
  Muestra emisor, instrumento, sector, país y región antes/después, los umbrales de Salud y la distancia a objetivos. **En memoria: no escribe nada, no estima rendimientos, no calcula impuestos.**

## Régimen macroeconómico
Estructura de los cuatro escenarios (reflación, expansión equilibrada, estanflación, desinflación) lista; **estado `no_disponible`**. La app sólo tiene CER, MEP, riesgo país e inflación de INDEC (Argentina): no alcanzan para el régimen global.
Falta: actividad, indicadores adelantados, inflación global, tasas, liquidez y condiciones financieras. Nada se inventa y no bloquea el análisis de precios.

## Señales (preparado para una segunda etapa)
`ciclos_historial.registrar` guarda, tras cada ingesta, el estado de cada grupo por **semana cerrada** y sólo si el grupo y su benchmark están completos y al día. `ciclos_senales_engine.detectar` (puro) identifica
`empieza_a_mejorar` (Lagging→Improving), `pasa_a_liderar` (Improving→Leading), `pierde_momentum` (Leading→Weakening) y `pierde_fortaleza_relativa`, cada uno confirmado o pendiente.
`GET /ciclos/grupos/{id}/senales` los expone. **No envía nada**: las alertas por Telegram quedan para la segunda etapa.

## API (`/api/inversiones`)

| | |
|---|---|
| `GET /ciclos/catalogo` · `GET /ciclos/estado` · `POST /ciclos/refrescar` | catálogo, cobertura por símbolo, descarga a mano |
| `GET /ciclos/panorama?tipo=&benchmark=&moneda=&periodo=&grupos=&ventana=&cola=` | mapa de rotación, calor, cambios, cobertura |
| `GET /ciclos/grupos/{id}?benchmark=&moneda=&horizonte=&periodo_id=&desde=&hasta=&con=` | ficha de un grupo |
| `GET /ciclos/grupos/{id}/senales` | cambios confirmados sobre el historial |
| `GET /ciclos/paises/{id}?meses=&benchmark=&moneda=` | ficha de país o región |
| `GET /ciclos/relaciones/correlaciones` · `/desfases` · `/comparacion` | relaciones |
| `GET /carteras/{n}/ciclos/cartera` · `/consolidado/ciclos/cartera` | capital por estado del ciclo |
| `GET …/ciclos/grupos/{id}/instrumentos` | posiciones del grupo, por emisor |
| `POST …/ciclos/simular` (`{origen, destino, pct, benchmark}`) | simulador (404 grupo inexistente, 422 valores inválidos) |

Cada respuesta incluye `meta`: fuente, última actualización, último dato, período, moneda, tipo de rendimiento, benchmark, limitaciones y advertencias.

## Agregar o corregir grupos y proxies
Se edita `catalogos/ciclos_grupos.json` (volumen del contenedor; no hace falta reconstruir, el archivo se relee al cambiar). Campos: `id`, `nombre`, `tipo`
(`sector|industria|commodity|region|pais|activo|tema`), `padre`, `proxy` (símbolo de Yahoo) o `sintetico`, `benchmark`, `moneda`, `tipo_rendimiento` (`total|precio`), `exclusivo`, `activo`, `vistas`,
`eje_cartera` (categorías excluyentes) y `cartera` (reglas superpuestas), y en países `indice_local`/`fx`. Un grupo inválido se descarta **solo** (y lo que depende de él) y se informa en `errores` de `GET /ciclos/catalogo`.
Para corregir un proxy alcanza con cambiar `proxy`; los algoritmos no conocen ningún símbolo. Antes de habilitar uno nuevo:

```bash
docker compose exec backend python -m scripts.verificar_ciclos              # cobertura real por símbolo y horizonte
docker compose exec backend python -m scripts.verificar_ciclos --inactivos  # prueba también los activo:false (no guarda)
```
Lo que no baje se deja en `activo: false` con una `nota`.

## Correr y probar

```bash
docker compose -f docker-compose.yml -f docker-compose.corporate.yml up --build
curl -X POST http://localhost:8087/api/inversiones/ciclos/refrescar     # primera vez: ~1,5 min para ~66 símbolos
curl http://localhost:8087/api/inversiones/ciclos/estado

docker compose -f docker-compose.yml -f docker-compose.corporate.yml run --rm \
  -v $(pwd):/repo -w /repo -e PYTHONPATH=/repo/backend --no-deps backend \
  python -m pytest backend/tests/test_ciclos_*.py -q -p no:warnings
```

## Limitaciones
- Cada grupo se mide con **un proxy** (ETF o índice): no es el sector o mercado completo.
- Los ETFs de **futuros** (petróleo, gas, agrícolas, dólar) incluyen el efecto del roll y no son el precio spot.
- Bitcoin y Ethereum son precio spot; los índices locales de países son de precio. Si se mezclan con retorno total en una comparación, la pantalla lo avisa.
- Yahoo es una fuente no oficial: puede tener huecos o atrasos (ver «Cobertura real»).
- El rendimiento pasado no anticipa el futuro; el cuadrante describe las últimas semanas.
- Sin valuación, sin contexto macro global y sin tasas: son dimensiones distintas que este mapa no mide.

## Pendiente (segunda etapa)
Régimen macro con una fuente documentada · alertas por Telegram sobre `ciclos_senales_engine` · efectividad histórica de cada estado sobre `ciclos_estado_historial` · tasas de interés para el par «tasas → crédito» ·
holdings de ETFs para una clasificación temática de fuente externa.
