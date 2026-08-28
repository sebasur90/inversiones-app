# Guía de Desarrollo - Inversiones App

## Modos de Ejecución

La aplicación puede ejecutarse en dos modos:

### 1. **Modo Local (Excel)** - Para desarrollo en smoa7001lx
```
USE_LOCAL_SHEET=true
```
- Lee datos desde `sheet_local/sheet_inversiones.xlsx`
- No requiere conexión a Google Sheets API
- Ideal para desarrollo cuando hay limitaciones de proxy corporativo
- **Actualmente configurado por defecto en docker-compose.yml**

### 2. **Modo Google Sheets** - Para producción
```
USE_LOCAL_SHEET=false
```
- Lee datos directamente desde Google Sheets
- Requiere:
  - Archivo de credenciales en `credentials/google-service-account.json`
  - Conexión a internet sin bloqueos de proxy

## Cambiar Modo de Operación

### Para usar Google Sheets:
1. Editar `docker-compose.yml`
2. Cambiar: `- USE_LOCAL_SHEET=true` → `- USE_LOCAL_SHEET=false`
3. Reconstruir: `docker compose down && docker compose up -d --build`

### Para usar Excel local (default):
- Todo ya está configurado, solo ejecutar:
  ```bash
  docker compose up
  ```

## Estructura de Archivos

```
inversiones-app/
├── sheet_local/
│   └── sheet_inversiones.xlsx    # Datos locales (3 hojas + opcionales)
│       ├── Movimientos           # Transacciones
│       ├── Instrumentos          # Metadata de tickers
│       ├── Precios               # Series históricas
│       ├── Objetivos             # Opcional: metas financieras por cartera
│       ├── Rebalanceo            # Opcional: % objetivo de asignación
│       ├── Benchmarks            # Opcional: series de benchmarks (además de los automáticos)
│       ├── Configuracion         # Opcional: benchmark/pesos objetivo por cartera
│       └── Tipos de Cambio       # Opcional: CER/MEP dedicados (Fecha, Tipo, Valor)
├── credentials/
│   └── google-service-account.json  # Para modo Google Sheets
└── backend/
    └── app/services/
        ├── sheets_client.py       # Implementación (detecta USE_LOCAL_SHEET)
        └── market_data/           # APIs externas gratuitas (detecta USE_EXTERNAL_APIS)
```

## CER/MEP y benchmarks automáticos (USE_EXTERNAL_APIS)

```
USE_EXTERNAL_APIS=true   # default en docker-compose.yml y docker-compose.corporate.yml
```

Con el flag prendido, el sync completa automáticamente lo que el Sheet no cubre, usando APIs
gratuitas y sin API key (ver `backend/app/services/market_data/`):

- **CER/MEP diario**: [ArgentinaDatos](https://argentinadatos.com/docs/) (índice UVA como
  deflactor equivalente al CER, y dólar MEP histórico). Antes, si faltaba el MEP de una fecha
  el movimiento se descartaba en silencio; con la serie diaria eso deja de pasar.
- **Benchmark "Inflación (INDEC)"**: índice mensual construido por interés compuesto sobre la
  inflación publicada por ArgentinaDatos. Activa Performance relativa, Comparar benchmarks y el
  Sharpe de Riesgo con un benchmark real además de Dólar (MEP) e Inflación (CER).

**El Sheet siempre gana**: estos valores sólo completan huecos, nunca pisan una fecha que ya
esté cargada a mano (en `Movimientos`, `Precios`, `Tipos de Cambio` o `Benchmarks`). Si la API
no responde (proxy caído, sin internet), el sync no falla: queda una advertencia en Calidad de
datos y se preserva lo último que sí se pudo traer. Para apagarlo (comportamiento 100% manual,
como antes), `USE_EXTERNAL_APIS=false`.

No se automatizaron MERVAL, S&P 500 ni una tasa libre de riesgo histórica: no encontramos una
API gratuita y confiable con esas series (Stooq bloquea el acceso programático con un desafío
JS, y no hay endpoint público con el nivel histórico del MERVAL). Para esos casos seguí
cargando la pestaña `Benchmarks` a mano.

## Sincronización en la UI

Independientemente del modo:
- Click en "Sincronizar" lee los datos
- POST `/api/inversiones/sync`
- Timeouts configurados a 300s (5 min) para operaciones largas

## Notas

- El archivo Excel debe tener las mismas 3 hojas: Movimientos, Instrumentos, Precios
- Las columnas deben coincidir exactamente con el Google Sheet original
- En modo local no se requiere acceso a internet

## Precio Objetivo y Stop Loss

La pestaña `Instrumentos` admite 4 columnas opcionales para fijar, por ticker, un precio
objetivo (para tomar ganancias) y un stop loss (para cortar pérdidas). Deben coincidir
exactamente en el Google Sheet y en `sheet_local/sheet_inversiones.xlsx`:

| Columna | Valores | Significado |
|---|---|---|
| `Objetivo Modo` | `Porcentaje` o `Fijo` | cómo interpretar `Objetivo Valor` |
| `Objetivo Valor` | número | `Porcentaje`: % sobre el precio promedio de compra (ej. `20` = +20%). `Fijo`: precio absoluto |
| `Stop Loss Modo` | `Porcentaje` o `Fijo` | cómo interpretar `Stop Loss Valor` |
| `Stop Loss Valor` | número | `Porcentaje`: % de caída sobre el precio promedio de compra (ej. `-5`). `Fijo`: precio absoluto |

`Modo` y `Valor` deben completarse juntos (o dejarse ambos vacíos). Se ven en el detalle de
cada ticker en la app, junto con el % que falta para alcanzarlos.

## Rebalanceo de Cartera

La pestaña opcional `Rebalanceo` define los porcentajes objetivo de asignación de la
cartera, en 3 ejes independientes (cada uno suma 100% por su cuenta). Debe coincidir
exactamente en el Google Sheet y en `sheet_local/sheet_inversiones.xlsx`. No es lo mismo
que `Objetivo Modo/Valor` de `Instrumentos` (eso es el precio objetivo de venta de un
ticker puntual, no tiene relación con esta pestaña).

| Columna | Valores | Significado |
|---|---|---|
| `Cartera` | nombre de cartera, `Consolidado`, o vacío | A qué alcance aplica el objetivo. Vacío/`Consolidado` = patrimonio total. |
| `Eje` | `Cartera`, `Tipo` o `Sector` | Qué se está repartiendo. `Cartera` solo es válido con `Cartera` vacío/`Consolidado`. |
| `Categoría` | texto libre | Nombre de la cartera (eje `Cartera`), del Tipo Instrumento o del Sector, según corresponda. |
| `Porcentaje Objetivo` | número 0-100 | % objetivo dentro de ese eje y ese alcance. |

Si no se define una fila para una categoría con valor invertido real, esa categoría se
muestra en la app como "Sin objetivo" (con su valor/% actual, sin comparación). Si la
pestaña no existe todavía, la sincronización no falla — simplemente no hay objetivos
cargados. Se ve en la pestaña "Rebal." del nav inferior.

