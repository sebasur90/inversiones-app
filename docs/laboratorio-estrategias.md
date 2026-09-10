# Laboratorio de estrategias

Prototipar una estrategia técnica en un notebook, exportar el **DSL JSON canónico** y importarlo
a la app. La estrategia sigue siendo el mismo DSL que persiste en SQLite, valida
`validar_estrategia` y re-evalúa la watchlist para dar señales en vivo — el laboratorio sólo
agrega una forma cómoda de escribirlo y verificarlo.

**No se ejecuta código del usuario en el backend.** Lo que viaja entre el lab y la app es un
archivo JSON.

---

## Levantar el lab

```bash
# Perfil opcional: NO arranca con un `docker compose up` normal.
docker compose --profile lab up lab
# corporativo:
docker compose -f docker-compose.yml -f docker-compose.corporate.yml --profile lab up lab
```

Abrir **http://127.0.0.1:8888**. El puerto se publica sólo en `127.0.0.1` (ver el `ports:` del
servicio `lab` en `docker-compose.yml`), y por eso el servidor va sin token: Jupyter ejecuta
código arbitrario como root con la DB de la cartera montada, así que **no** debe publicarse en
`0.0.0.0` ni quedar accesible desde la LAN. Los notebooks viven en `lab/`; las
estrategias exportadas en `lab/estrategias/*.json` (no se versionan). El lab monta la base de la
app en **solo lectura**: nunca escribe.

Sin Jupyter, el mismo flujo como script:

```bash
docker compose exec backend python -m scripts.lab_ejemplo AAPL
docker compose exec backend python -m scripts.lab_ejemplo AAPL --variante subyacente --desde 2015-01-01
```

---

## Catálogo de indicadores

Todos se instancian con `ind.<TIPO>(...)`. `ventana=0` en EXTREMOS/PERCENTIL = ventana expansiva
desde el inicio de la serie cargada (histórico acumulado).

| tipo | params (default) | salidas | warm-up |
|---|---|---|---|
| `SMA` | `periodo=50` | `valor` | `periodo` |
| `EMA` | `periodo=20` | `valor` | `periodo` |
| `RSI` | `periodo=14` | `valor` | `periodo + 1` |
| `MACD` | `rapida=12, lenta=26, senal=9` | `macd`, `senal`, `histograma` | `lenta + senal` |
| `BOLLINGER` | `periodo=20, desvios=2.0` | `media`, `superior`, `inferior`, `ancho_pct`, `pctb` | `periodo` |
| `ATR` | `periodo=14` | `valor` | `periodo + 1` |
| `ESTOCASTICO` | `periodo_k=14, suavizado_k=3, periodo_d=3` | `k`, `d` | suma de los tres |
| `OBV` | — | `valor` | 1 |
| `VOLUMEN_PROMEDIO` | `periodo=20` | `valor` | `periodo` |
| `EXTREMOS` | `ventana=20` (rango 0..500) | `maximo`, `minimo`, `medio`, `dist_max_pct`, `dist_min_pct` | `ventana`, o todo el histórico con `ventana=0` |
| `PERCENTIL` | `ventana=100` (rango 0..500) | `valor` | idem |
| `RETORNO` | `periodo=20` | `valor` | `periodo + 1` |

**EXTREMOS** — canal de Donchian sobre `(máximo, mínimo)` de la barra (o el cierre, sin OHLC),
incluyendo la barra actual, sin lookahead.
`dist_max_pct = (cierre/máximo − 1)·100` (≤ 0, cero en un máximo nuevo);
`dist_min_pct = (cierre/mínimo − 1)·100` (≥ 0, cero en un mínimo nuevo).
`dist_max_pct` con `ventana=0` **es** el drawdown desde el máximo histórico; con `ventana=252`,
el de 52 semanas. No hay un indicador `DRAWDOWN` aparte: sería el mismo cálculo.

**PERCENTIL** — rank real: `100 · #{cierres de la ventana < cierre actual} / (W − 1)`. 0 exacto
en el mínimo de la ventana, 100 en el máximo; resiste outliers. No es min-max (eso *es*
`ESTOCASTICO(N,1,1).k`).

**Alcance de "histórico"**: `ventana=0` es *desde el inicio de la serie cargada*, no desde el
debut del instrumento. Su warm-up pide toda la historia disponible. Consecuencia: la primera
barra de la serie es su propio máximo y mínimo, así que `dist_min_pct` y `dist_max_pct` valen 0
ahí — usá un `desde` razonable.

---

## Referencia del builder

```python
from app.lab import Estrategia, ind, precio, entre, todas, alguna, negar
from app.lab import barras_de_db, barras_de_dataframe, correr_como_la_app, comparar_con_mascara
```

### Operandos

- `precio.cierre`, `precio.apertura`, `precio.maximo`, `precio.minimo`, `precio.volumen`
- `ind.SMA(50)` (mono-salida: es operando por sí mismo)
- `ind.MACD().macd`, `ind.EXTREMOS(0).dist_min_pct` (multi-salida: elegís la salida por atributo)
- números crudos → `{"const": n}`

### Operadores

| Python | DSL |
|---|---|
| `<` `<=` `>` `>=` | comparadores `menor` / `menor_igual` / `mayor` / `mayor_igual` |
| `&` `\|` `~` | `y` / `o` / `no` |
| `a.cruza_arriba(b)` / `a.cruza_abajo(b)` | `cruce_arriba` / `cruce_abajo` |
| `a.subiendo(barras=1)` / `a.bajando(...)` | `subiendo` / `bajando` |
| `entre(x, a, b)` | `entre` |
| `todas(...)` / `alguna(...)` / `negar(...)` | formas explícitas de `y` / `o` / `no` |

**`and` / `or` / `not` / `if cond:` / `1 < x < 2` levantan `TypeError`**: Python los convierte en
booleanos y `a and b` devolvería `b` en silencio. Usá siempre `&` `|` `~`.

`a & b & c` se aplana a un solo nodo `y` con tres hijos (el validador comparte un presupuesto de
20 nodos entre entrada y salida). `~~a` → `a`.

### Estrategia

```python
est = (Estrategia("Nombre", descripcion=None)
       .comprar(condicion)                 # obligatorio
       .vender(condicion)                  # opcional
       .riesgo(stop_loss_pct=20, take_profit_pct=None, trailing_stop_pct=None, max_barras=None)
       .ejecucion(comision_pct=0.6, precio_ejecucion="apertura_siguiente", demora_barras=1))

est.definicion()   # dict DSL, ya validado (== est.a_dict())
est.a_json()       # str
est.dataframe(barras)   # OHLCV + una columna por salida de indicador + entrada/salida
est.backtest(barras)    # ResultadoLab (motor puro)
est.exportar("estrategias/mi-estrategia.json")   # el sobre JSON
```

`definicion()` / `a_json()` / `backtest()` / `exportar()` corren `validar_estrategia` y levantan
`EstrategiaInvalida` (subclase de `ValueError`): nada sale del lab sin ser válido. Los ids de los
indicadores son determinísticos (`SMA(50)` → `sma_50`); dos `ind.SMA(50)` sueltos colapsan en uno.

### Datos

- `barras_de_db(ticker, desde=None, hasta=None, variante="local")` — la serie **exacta** de la
  app (`ohlcv_analytics.get_serie_barras`): mismas velas, feriados y variantes. `variante`:
  `"local"` (como cotiza) o `"subyacente"` (USD del subyacente).
- `barras_de_dataframe(df, columnas={...})` — adaptador genérico para prototipar sobre cualquier
  DataFrame. Las columnas OHLCV que falten quedan en `None` (el motor degrada a `(cierre, cierre)`).

### Verificar antes de exportar

```python
salida = correr_como_la_app(ticker, est, desde=..., variante=...)
salida["metricas"]
```

`correr_como_la_app` llama directo a `estrategias_analytics.ejecutar_backtest`: cero duplicación
de la lógica de warm-up / `indice_inicio` / `max_barras`. **Las métricas tienen que coincidir con
las del backtest en la app** después de importar el JSON. Si difieren, hay una discrepancia real
en cómo el lab resuelve la serie.

### Máscaras de pandas

El builder **no** traduce máscaras booleanas al DSL: una máscara es un vector de resultados, no
una expresión, y `df.cierre.shift(-1)` abriría la puerta al lookahead. El camino inverso sí:

```python
mascara = df["cierre"] <= df["cierre"].cummin() * 1.01
comparar_con_mascara(est, barras, mascara)   # barras donde tu máscara difiere del DSL
```

---

## El sobre JSON y su versionado

```json
{
  "formato": "inversiones-app/estrategia",
  "formato_version": 1,
  "exportado_en": "2026-09-07T12:00:00Z",
  "nombre": "Mínimo histórico",
  "descripcion": null,
  "ticker": null,
  "variante": "local",
  "definicion": { "version": 1, "indicadores": [], "entrada": {} }
}
```

Dos versiones a propósito: `formato_version` (el sobre) y `definicion.version` (el DSL). El
importador de la app **también acepta un DSL crudo** (tiene `version` y `entrada` en la raíz, no
tiene `definicion`), así pegar el `definicion` de un preset o de una respuesta de la API funciona
sin fricción. `ticker: null` es lo que hace la estrategia reusable en cualquier activo.

Al importar en **Análisis técnico → Estrategias → Importar JSON**: se adoptan
`nombre`/`descripcion`/`variante` y se corre el backtest al toque (un DSL inválido dispara el 422
ahí mismo). El ticker de la página **no** cambia aunque el archivo traiga otro — sólo se avisa si
difieren.

Al guardar, **el nombre identifica a la estrategia**: si ya existe una guardada con ese nombre
(ignorando mayúsculas y acentos), se sobrescribe en vez de crear una segunda con el mismo texto, y
la app avisa que la pisó. Así, reexportar desde el notebook y reimportar la misma estrategia N
veces deja una sola fila, no N. Para quedarte con las dos versiones, cambiale el nombre a una
(o usá "Duplicar", que busca el primer `… (copia)`, `… (copia) (2)` libre).

---

## Limitaciones

- **Sin lookahead**: el DSL por construcción no puede mirar barras futuras (el validador incluso
  bloquea `apertura_siguiente` con `demora_barras=0`).
- **Límites del validador**: 20 nodos y profundidad 4, **compartidos entre entrada y salida**.
- **Alcance de "histórico"**: `ventana=0` es desde el inicio de la serie cargada (ver arriba).
- **Condiciones no editables en el editor visual**: `no`, `entre`, `subiendo`, `bajando` y el
  anidamiento de `y`/`o`. Una estrategia importada con esas condiciones se edita en un panel
  avanzado de solo lectura (con backtest y guardado normales); sólo riesgo y ejecución son
  editables sin pérdida. "Editar igual" pasa al editor visual descartando esas condiciones, con
  confirmación.
- El Segmented de "Precio de ejecución" fija `demora_barras` a 0/1: un DSL importado con
  `demora_barras: 3` se conserva sólo mientras no toques ese control.
