# Centro de Decisiones

Pantalla `/decisiones` (menú **Más → Decisiones**, el buscador global, el botón **Analizar decisión** de la
pestaña Pares de la ficha y el ícono de brújula en Posiciones). Ayuda a buscar oportunidades, comparar un activo
con alternativas, evaluar posiciones abiertas, simular decisiones sin tocar la cartera y llevar un diario de
decisiones con revisiones y aprendizaje.

**No opera ni registra movimientos.** La fuente de verdad sigue siendo el Google Sheet / Excel. Todo lo nuevo vive
en tablas propias que el sync no toca.

## Arquitectura

```
routers/decisiones.py
  └─ services/centro_decisiones_analytics.py   (orquestador: un Universo por pedido, secciones que degradan solas)
       ├─ valuacion_analytics  → diagnóstico de empresa (pares automáticos)
       ├─ comparador_analytics → alternativas comparables (+ comparador_engine.rankear para evaluarlas igual)
       ├─ valor_razonable_analytics → rango pesimista/base/optimista por múltiplos de pares
       ├─ lectura_tecnica (servicio nuevo, extraído del router técnico) + ATR(14)
       ├─ decision_datos       → volatilidad y caída máxima de la serie semanal (USD), fuentes y fechas
       ├─ simulador_decision   → compra / venta / reducción / reasignación en memoria
       ├─ evaluacion_engine    → puntajes por dimensión, pesos, banderas, orden, conclusión   (puro)
       ├─ escenarios_entrada_engine → entrar ahora / esperar / escalonar / descartar          (puro)
       ├─ posicion_decision_engine  → mantener / aumentar / reducir / salir                    (puro)
       └─ interpretacion       → resumen en plantillas + `validar_cifras`
  └─ services/diario_decisiones.py (guardar, revisar, pendientes, aprendizaje, aviso Telegram)
       ├─ revision_engine     (puro)
       └─ aprendizaje_engine  (puro)
```

Tablas nuevas (`create_all`, sin tocar datos existentes): `decision_preferencias`, `decisiones`,
`decision_alternativas`, `decision_snapshots`, `decision_revisiones`. Columna nueva:
`ajustes_avisos.avisar_revision_decision` (ALTER idempotente, default 1). Ninguna referencia ids de
`movimientos_inversion` (el sync los regenera): se vinculan por ticker + fecha.

## Endpoints (`/api/inversiones`)

| Método | Ruta | Qué hace |
|---|---|---|
| GET/PUT | `/decisiones/preferencias` | horizonte, objetivo, enfoque, tolerancia, moneda, universo, exclusiones, pesos |
| GET | `/decisiones/facetas` | sectores/industrias/países/regiones/tipos reales, temáticas por regla y cobertura |
| GET | `/decisiones/explorar?sector=&pais=&region=&industria=&tipo=&tematica=` | ranking sin técnico ni encaje |
| GET | `/decisiones/analisis/{ticker}?cartera=&con=A,B&monto_ref_usd=` | análisis completo |
| GET | `/decisiones/posicion/{ticker}?cartera=` | mantener / aumentar / reducir / salir |
| POST | `/carteras/{n}/simular-decision`, `/consolidado/simular-decision` | `{operaciones: [{ticker, monto_usd ±}]}` |
| GET/POST | `/decisiones` | listar / guardar (el servidor re-corre el análisis) |
| GET/PATCH/DELETE | `/decisiones/{id}` | detalle (con foto inicial y revisiones) / campos del usuario / borrar |
| POST | `/decisiones/{id}/revisiones` | revisión nueva (no pisa nada) |
| PATCH | `/decisiones/revisiones/{id}` | el usuario califica su proceso |
| GET | `/decisiones/pendientes` | revisión vencida o invalidación de precio cumplida |
| GET | `/decisiones/aprendizaje` | patrones con muestra mínima |

Todos los parámetros de preferencias (`horizonte`, `objetivo`, `enfoque`, `moneda`, `tolerancia`) se pueden pasar
por query como override sin guardarlos.

## Motor de evaluación (`evaluacion_engine`, `VERSION_REGLAS = 1`)

Cinco dimensiones con puntaje 0–100. **Faltante = `None`, nunca 0**; "no aplica" (ETF sin fundamentales de negocio,
sin cartera para el encaje) sale del cálculo sin penalizar.

| Dimensión | Regla |
|---|---|
| Fundamentales | Promedio de calidad, crecimiento y solidez del diagnóstico de empresa. Cada una vale su percentil favorable (100 = la mejor del grupo); sin percentil, su nivel: bien 75 / neutro 50 / atención 35 / riesgo 15. |
| Valoración | Percentil favorable de la valuación contra pares (100 = la más barata). El valor razonable sale de los mismos múltiplos: no vota aparte, sólo ajusta ±5 (precio debajo / encima del rango). Sin percentil: debajo 65 / dentro 50 / encima 35. |
| Riesgo | Promedio de: volatilidad anual (≤ 25 % → 75, ≤ 40 % → 50, más → 25), caída máxima (> −30 % → 75, > −50 % → 50, más → 25), beta (≤ 1 → 70, ≤ 1,5 → 50, más → 30). Divisa: informativo. |
| Técnico | Promedio de tendencia vs SMA(50) (alcista 70 / mixta 50 / bajista 30), RSI(14) (neutral 55 / sobreventa 45 / sobrecompra 40) y fuerza relativa 63 ruedas (mejor 65 / parecida 50 / peor 35). Sólo cartera ∪ watchlist. |
| Encaje | 60 − 30 por observación «revisar» − 15 por «atención» (umbrales de Salud de cartera, con un monto de referencia = 5 % de la cartera). Objetivo ingresos: dividendo ≥ 2 % +15, menor −15. Diversificación: sector o país nuevo +10 c/u, emisor ya en cartera −10. |

**Pesos** (decisión de diseño configurable, no verdad financiera; suman 100):

| Enfoque / horizonte | Fund. | Val. | Riesgo | Técn. | Encaje |
|---|---|---|---|---|---|
| fundamental · corto / mediano / largo | 25 / 30 / 35 | 25 / 30 / 30 | 25 / 20 / 20 | 15 / 10 / 5 | 10 |
| técnico · corto / mediano / largo | 5 / 10 / 20 | 10 / 15 / 20 | 25 | 50 / 40 / 25 | 10 |
| combinado · corto / mediano / largo | 15 / 25 / 30 | 20 / 25 / 30 | 25 / 20 / 20 | 30 / 20 / 10 | 10 |

La tolerancia multiplica el peso de Riesgo (baja ×1,5, media ×1, alta ×0,5; sin definir ×1). El usuario puede
reemplazar la tabla por sus pesos.

**Orden** = Σ pesoᵢ·puntajeᵢ / Σ pesoᵢ sobre las dimensiones con dato. **Incompleto (sin número)** si esas
dimensiones cubren < 60 % del peso aplicable o la confianza del diagnóstico es baja. `contribuciones` explica qué
subió o bajó el orden.

**Banderas** (se muestran aunque el orden sea alto): solidez en riesgo (alta), pérdidas (alta), riesgo alto con
tolerancia baja (alta), ingresos cayendo > 2 %, payout > 100 %, fundamentales > 21 días, cotización > 7 días,
concentración «revisar», confianza baja.

**Conclusión** (en orden): datos insuficientes (orden incompleto) → riesgo elevado (bandera alta o Riesgo < 35) →
alternativa más atractiva (mejor orden supera al segundo por ≥ 10, sin banderas altas, firmeza del comparador
media/alta y el mismo ganador con los pesos de los tres enfoques) → valoración exigente (Valoración < 35) →
interesante pendiente (orden ≥ 60 con técnico o valoración < 50) → ninguna claramente superior. Responde siete
preguntas (qué encaja, por qué, evidencia, desventajas, invalidación, siguiente paso, incertidumbre) y siempre
trae evidencia en contra y preguntas para revisar la tesis.

**Alternativas**: miembros aptos del comparador (o `con`), cada uno re-diagnosticado contra los demás del grupo
(`comparador_engine.rankear`), con la misma base de riesgo (serie semanal en USD) y el mismo monto de encaje. Por
eso el puntaje del activo en la tabla puede diferir del de su análisis individual. Se avisa cuando los balances
difieren > 120 días o los fundamentales > 14 días.

## Escenarios de entrada (`escenarios_entrada_engine`)

- Precio de referencia: último cierre de la serie técnica (si existe) o el del snapshot de Yahoo; se guarda la fuente.
- Soporte: el automático más cercano debajo del precio (`niveles_auto_engine`).
- Invalidación: soporte − 1 ATR(14); sin soporte, entrada − 2 ATR(14). Sin ATR no se inventa.
- Esperar valoración: valor razonable base (o pesimista si el precio ya está debajo del base).
- Escalonada: tres tramos iguales en precio actual, soporte y soporte − 1 ATR.
- Potencial = (V − P) / P contra pesimista/base/optimista. **Hipotético**, relativo a pares, no rendimiento esperado.
- Riesgo = (I − P) / P. Comisión ida y vuelta = 2 × tasa promedio histórica (si no hay comisiones cargadas, se dice).
- Monedas distintas entre precio y valor razonable: no se comparan.

## Simulador (`simulador_decision`)

Montos en USD: positivos suman (aporte o reasignación), negativos reducen una tenencia (prorrata entre carteras en
el consolidado; más que la tenencia → 422). Lo liberado y no reasignado queda como "Liquidez (simulada)". Ejes:
Emisor (CEDEAR + acción + variantes = uno), Sector, País, Región, Tipo y Moneda. Por reducción: fracción, cantidad
estimada y resultado estimado = monto − fracción × costo de la tenencia (costo promedio, como Posiciones).
Distancia a los objetivos de Rebalanceo antes/después si hay objetivos cargados. **Impuestos: no calculados.**
`impacto-compra` no cambió; un test verifica que con una sola suma los ejes coinciden.

## Posición existente (`posicion_decision_engine`)

Cuatro opciones con evidencia a favor/en contra, cambio en la cartera (simulaciones de +25 %, −50 % y −100 % de la
posición), condiciones e invalidación. **El resultado de la posición nunca es evidencia** (la función ni lo
recibe; un test lo verifica comparando la misma posición en ganancia y en pérdida). Se compara contra la tesis de
la última decisión guardada (deterioro = una dimensión bajó ≥ 15 puntos o apareció una bandera alta). Mantener vs.
reasignar: la mitad a cada una de las tres mejores alternativas y la mitad a liquidez.

## Diario, revisiones y aprendizaje

- Guardar re-corre el análisis en el servidor y congela la salida completa (`decision_snapshots` tipo `inicial`).
  Del cliente sólo se toman parámetros y elecciones. Inmutable salvo `ejecutada`, `nota`, `revisar_el`, `estado`.
- Revisar: análisis de hoy con las mismas preferencias y alternativas; compara dimensiones, banderas nuevas y
  resueltas, precio en la misma fuente, índice del período (SPY en USD, Merval en ARS, si están en la base),
  alternativas, condiciones de invalidación, supuestos (confirmado / refutado / pendiente / a tu juicio) y
  volatilidad observada vs. la del día de la decisión. El resultado sólo si está marcada como ejecutada (y es
  aproximado por precio). Si hay movimientos del ticker posteriores sin marcar, se sugiere marcarla.
- Aprendizaje (calculado, no persistido): revisiones a tiempo, entradas contra la conclusión, entradas con banderas
  críticas, concentración recurrente, condiciones de invalidación definidas, expectativa vs. resultado, riesgo
  mayor al esperado, ideas invalidadas y, del diario de operaciones, compras cerca de máximos, ventas antes de
  subas y ventas cerca de mínimos. < 3 casos: no se dice; 3–9: descriptivo; ≥ 10: se repite. Nunca "estadístico".
- Aviso por Telegram (interruptor **Revisión de decisiones** en Ajustes → Avisos): después de cada evaluación de
  alertas del scheduler, una vez por evento (revisión vencida / invalidación de precio). Apagado, se marca igual.

## IA

No hay proveedor de IA en esta versión. Los textos salen de plantillas (`interpretacion.Plantillas`) que sólo usan
números calculados. `DECISIONES_INTERPRETADOR` queda reservado (hoy sólo `plantillas`). Toda frase del resumen pasa
por `validar_cifras`: un número que no exista en los datos estructurados descarta la frase (y se loguea). Es la
guarda que tendría que pasar un modelo de lenguaje futuro.

## Fuentes y limitaciones

- Fundamentales, múltiplos, beta, serie semanal: Yahoo vía la ingesta existente (`fundamentales_ingesta`, cada
  ~7/14 días por emisor). Sólo el último trimestre contra el mismo del año anterior: sin historia contable de
  varios años, sin múltiplos históricos propios, sin estimaciones de analistas en el cálculo.
- Técnico: sólo cartera ∪ watchlist (serie diaria). La pantalla ofrece agregar a la watchlist.
- Temáticas: sólo por reglas sobre datos que existen (dividendos, crecimiento, valor, calidad). "Inteligencia
  artificial" y similares no se ofrecen como temática: se busca por sector o industria.
- Bonos, ONs, letras y FCI: fuera de alcance.
- Comisiones: tasa histórica promedio. Impuestos: no se calculan.
