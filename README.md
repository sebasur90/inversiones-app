# Inversiones (extraído de movimientos)

Este directorio contiene todo el código relacionado al módulo de inversiones
(seguimiento de carteras, movimientos, objetivos de inversión) extraído de la
app "movimientos", listo para copiarse a un repo/proyecto nuevo y seguir
desarrollándose ahí de forma independiente.

## Qué incluye

**Backend** (`backend/app/`)
- `routers/inversiones.py` — endpoints de carteras, resumen, exposición, movimientos, sync, rendimiento por ticker.
- `routers/objetivos_inversion.py` — CRUD de objetivos de inversión + aportes históricos.
- `services/inversiones_sync.py` — sincroniza movimientos/instrumentos/precios desde Google Sheets.
- `services/inversiones_analytics.py` — cálculos de rendimiento, exposición, TWR, etc.
- `services/sheets_client.py` — cliente de Google Sheets (cuenta de servicio).
- `services/cotizaciones.py` — cotizaciones de dólar (dolarapi.com), usadas por analytics para convertir ARS/USD.
- `database.py` y `schemas.py` — copiados **completos** desde la app original, así que incluyen modelos/schemas de otras
  secciones (movimientos, categorías, jubilación, etc.) que no usa este módulo. Podés borrarlos con confianza; se
  dejaron así para que la app arranque sin romper imports. Lo que sí usa este módulo: `InstrumentoInversion`,
  `MovimientoInversion`, `PrecioInstrumento`, `IndiceMercado`, `ObjetivoInversion`, `TipoCambio`, `IndicadorEconomico`.
- `main.py` — **reescrito**, no es una copia. Solo registra los routers de inversiones y el fetch de cotizaciones al
  arrancar (no incluye el resto de routers/seed de la app original).

**Frontend** (`frontend/src/`)
- `pages/Inversiones.tsx` — página principal con tabs (resumen, movimientos, objetivo).
- `hooks/useInversiones.ts`, `hooks/useObjetivoInversion.ts`.
- `components/inversiones/*` — KPIs, gráficos (comparación, exposición, aportes históricos), tablas, modal de objetivo, drawer de detalle de ticker.
- `api/index.ts` — copiado **completo** desde la app original (incluye llamadas de otras secciones). Las funciones
  relevantes son las de la sección `// ---- Inversiones ----` en adelante.
- `utils.ts` — formatters (`formatARS`, `formatUSD`, `formatPct`, etc.) y paleta de colores, usados por los gráficos.
- `App.tsx`, `main.tsx` — **reescritos** como scaffold mínimo: solo montan `<Inversiones />` con el tema dark de antd
  (no incluyen el router ni el layout con sidebar de la app original).

## Configuración necesaria

- **Google Sheets**: `sheets_client.py` espera un archivo de cuenta de servicio en
  `backend/data/google-service-account.json` (o la ruta que indiques en `GOOGLE_SERVICE_ACCOUNT_FILE`), con acceso de
  lectura al spreadsheet `SPREADSHEET_ID` definido en ese archivo (pestañas `Movimientos`, `Instrumentos`, `Precios`).
  Actualizá ese ID si vas a usar otro Sheet.
- **CORS**: variable de entorno `CORS_ORIGINS` (default apunta a `localhost:5173`/`localhost:80`).
- **Base de datos**: SQLite, se crea sola en `backend/data/data.db` al arrancar (`init_db()`).

## Cómo correrlo

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

O con Docker: `docker compose up --build` desde la raíz de esta carpeta.

## Pendiente al migrar

- Limpiar de `database.py` y `schemas.py` los modelos/schemas que no son de inversiones (opcional, no rompe nada
  dejarlos).
- Limpiar de `api/index.ts` las funciones de otras secciones si querés un cliente HTTP más chico.
- No se copiaron datos: ni `data.db` ni las credenciales de Google ni los PDFs de resúmenes de cuenta.
- Si querés navegación/routing, layout con sidebar, etc., hay que armarlo de nuevo — `App.tsx` acá es un scaffold
  mínimo de una sola página.
