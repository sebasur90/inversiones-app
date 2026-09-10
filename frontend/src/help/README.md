# Sistema de Ayuda Contextual — Referencia

Este directorio centraliza todo el contenido y componentes del sistema de ayuda contextual de la app:
el glosario término por término (`InfoTooltip`), las guías por pantalla (`GuiaPantalla`), el tour de
bienvenida (`TourBienvenida`) y el Centro de ayuda (`pages/Ayuda.tsx`, fuera de este directorio por
ser una pantalla y no un componente reutilizable).

## Estructura

- **`types.ts`** — Definición de `HelpContent` (un término) y `GuiaPantalla` (una pantalla entera)
- **`content/`** — Contenido editable (separado de presentación)
  - `glosario.ts` — términos generales del glosario
  - `simulador.ts`, `objetivo.ts`, `benchmarks.ts`, `patrimonio.ts`, `calidaddatos.ts`,
    `diagnostico.ts`, `movimientos.ts`, `posiciones.ts`, `exposicion.ts`, `vencimientos.ts`,
    `precios.ts`, `indicadoresmacro.ts`, `comparador.ts`, `performancerelativa.ts`,
    `tickerdetalle.ts`, `comisiones.ts`, `rebalanceo.ts`, `flujocaja.ts`, `watchlist.ts`,
    `analisisTecnico.ts`, `estrategias.ts` — keys por pantalla, cada una con su propio archivo
  - `index.ts` — Combina todo en un Record único (`HELP`) y expone el alias `HelpKey`
  - `guias.ts` — `GUIAS_PANTALLA`: una guía "Cómo leer esta pantalla" por ruta, resuelta por
    `useLocation().pathname` (no se toca cada página para agregar/editar una)
  - `tour.ts` — Los pasos del tour de bienvenida
  - `tutoriales.ts` — Recorridos paso a paso multi-pantalla, para el Centro de ayuda
  - `faq.ts` — Preguntas frecuentes, para el Centro de ayuda
- **`components/`** — Componentes reutilizables
  - `InfoTooltip.tsx` — Botón "(i)" + Modal con secciones; exporta también `InfoTooltipLink`
    (chip que abre el mismo modal, usado por `GuiaPantalla` y el buscador) y `ContenidoTermino`
    (el cuerpo del modal en sí, para reusar fuera de un tooltip — p. ej. el glosario del Centro
    de ayuda)
  - `FormHelp.tsx` — Wrapper sobre InfoTooltip + rango de validación
  - `GuiaPantalla.tsx` — Banner colapsable "💡 Cómo leer esta pantalla", montado una sola vez en
    `ScreenHeader` y resuelto por ruta contra `content/guias.ts`
  - `TourBienvenida.tsx` — Modal-carrusel de bienvenida; estado (`tourAbierto`) vive en
    `InversionesContext`, igual que `syncSheetOpen`
  - `ScenarioIntentBanner.tsx` — Callout "¿Qué estás haciendo?" / "¿Qué vas a obtener?"
  - `ResultInterpretation.tsx` — Bloque "🔎 Interpretación" post-resultado
  - `ErrorBanner.tsx` — Presentación visual de ParsedApiError
- **`errors/`** — Manejo de errores amigables
  - `escenarioLimits.ts` — Espejo de límites de `backend/app/schemas.py` (fuente única de verdad en frontend)
  - `apiErrors.ts` — `parseApiError()` que maneja errores Pydantic y customizados

## Fuera de `help/` pero parte del mismo sistema

- **`pages/Ayuda.tsx`** (`/ayuda`) — Centro de ayuda: tutoriales (`content/tutoriales.ts`),
  glosario buscable (sobre `HELP`), preguntas frecuentes (`content/faq.ts`) y acceso al tour.
- **`components/ui/Semaforo.tsx`** + **`utils/niveles.ts`** — "bien/atención/riesgo" en palabras,
  no sólo color, para drawdown, volatilidad, concentración (HHI) y los scores de salud/calidad.
  Los umbrales de drawdown/volatilidad/concentración son los mismos que ya dispara
  `backend/app/services/diagnostico_engine.py` para generar un hallazgo.
- **`hooks/usePreferencia.ts`** — `CLAVE_MODO_GUIADO`, `CLAVE_TOUR_VISTO`,
  `PREFIJO_GUIA_COLAPSADA` y `limpiarGuiasColapsadas()`: el interruptor de Ajustes y la
  persistencia de qué guías quedaron colapsadas.

## Uso

### Para mostrar un help term en cualquier lugar

```tsx
import InfoTooltip from '../help/components/InfoTooltip'

<label>
  Mi métrica
  <InfoTooltip term="costoOportunidad" />
</label>
```

### En un formulario con rango de validación

```tsx
import FormHelp from '../help/components/FormHelp'

<FormHelp term="escenario_horizonte" label="Horizonte (meses)" />
<input type="number" min={1} max={360} />
```

### Manejo de errores del backend

```tsx
import { parseApiError } from '../help/errors/apiErrors'
import ErrorBanner from '../help/components/ErrorBanner'

try {
  await backend.post('/endpoint', data)
} catch (err) {
  const parsed = parseApiError(err, { 
    'variacion_por_defecto_pct': 'Variación por defecto'
  })
  setError(parsed)
}

// En JSX:
{error && <ErrorBanner error={error} />}
```

## Agregar ayuda a una nueva pantalla (checklist de 5 pasos)

1. **Identificar elementos que necesitan ayuda**
   - Métricas simples → `MetricTile` + `infoTerm`
   - Campos de formulario → `FormHelp`
   - Gráficos → `InfoTooltip` en el título
   - Resultados → `ResultInterpretation` para lógica compleja

2. **Crear archivo de contenido**
   - `help/content/<pantalla>.ts` con todas las keys en un solo lugar
   - Nunca dejar texto de ayuda inline en JSX

3. **Agregar imports** en el componente
   ```tsx
   import InfoTooltip from '../help/components/InfoTooltip'
   import FormHelp from '../help/components/FormHelp'
   ```

4. **Aplicar parseApiError si hay llamadas al backend**
   - Importar `parseApiError` y `ErrorBanner`
   - Envolver catch blocks visibles al usuario
   - Usar `escenarioLimits.ts` como referencia de límites

5. **Verificar en Docker**
   ```bash
   docker compose up
   # Navegar a la pantalla y confirmar que (i) aparecen y modales se abren
   ```

## Pantallas pendientes (Fase 2+)

| Pantalla | Estado | Prioridad | Notas |
|---|---|---|---|
| Patrimonio | ✅ | ✓ | MetricTile + patrimonio.ts + ErrorBanner (Batch 1) |
| Riesgo | ✅ | ✓ | MetricTile + ErrorBanner + InfoTooltip; reutiliza glosario (Batch 1) |
| Resumen | ✅ | ✓ | InfoTooltip + ErrorBanner en diagnóstico/calidad (Batch 1) |
| CalidadDatos | ✅ | ✓ | InfoTooltip para health_score/errores/advertencias; 5 términos (Batch 2) |
| Diagnostico | ✅ | ✓ | ErrorBanner + InfoTooltip para salud/dimensiones; 6 términos (Batch 2) |
| Movimientos | ✅ | ✓ | 9 términos + InfoTooltip inline (Batch 3 Sprint 1) |
| Posiciones | ✅ | ✓ | 9 términos + InfoTooltip inline (Batch 3 Sprint 1) |
| Exposición | ✅ | ✓ | 6 términos + sección informativa (Batch 3 Sprint 2) |
| Vencimientos | ✅ | ✓ | 5 términos + sección informativa (Batch 3 Sprint 3) |
| Precios | ✅ | ✓ | 6 términos + sección informativa (Batch 3 Sprint 4) |
| IndicadoresMacro | ✅ | ✓ | 2 términos nuevos + sección CER/MEP (Batch 4 Sprint 1) |
| Comparador | ✅ | ✓ | 2 términos nuevos + reutiliza precios_usd_mep/cer (Batch 4 Sprint 2) |
| PerformanceRelativa | ✅ | ✓ | 3 términos nuevos + pp global + reescrita costoOportunidad + MetricCard→MetricTile (Batch 5 Sprint 1) |
| TickerDetalle (Resumen/Rendimiento/Riesgo) | ✅ | ✓ | 2 términos nuevos + conexión cer (Batch 5 Sprint 2) |
| TickerDetalle (Histórico) | ✅ | ✓ | 2 términos nuevos + tooltips en headers tabla (Batch 5 Sprint 3) |
| Comisiones | ✅ | ✓ | 3 términos nuevos (Batch 6 Sprint 1) |
| Rebalanceo | ✅ | ✓ | 4 términos nuevos + migración InfoTerm→InfoTooltip (Batch 6 Sprint 2) |

## Notas para mantainers

- **Cambios en backend de validación**: actualizar `escenarioLimits.ts` línea que apunta a `backend/app/schemas.py:136-149`
- **Cambios en umbrales de `diagnostico_engine.py`** (drawdown/volatilidad/concentración): actualizar también `utils/niveles.ts`, que los replica a propósito para no inventar un criterio nuevo
- **Agregar una guía de pantalla nueva**: una entrada más en `content/guias.ts` — no hace falta tocar la pantalla en sí, `ScreenHeader` ya renderiza `GuiaPantalla` en todas
- **Agregar un tutorial o una FAQ**: una entrada más en `content/tutoriales.ts` o `content/faq.ts`; aparecen solas en el Centro de ayuda
- **EmptyState.tsx**: no se toca salvo necesidad puntual — la mayoría ya explica qué falta y cómo resolverlo, no hace falta un texto genérico "Sin datos"

## Referencias

- Plan original (Fase 1): `/home/slrodriguez/.claude/plans/sistema-de-peaceful-quasar.md`
- Estado de implementación (Fase 1): `/home/slrodriguez/.claude/projects/-home-slrodriguez-inversiones-app/memory/plan_ayuda_fase1_avance.md`
- Plan de onboarding (guías, tour, Centro de ayuda): `/home/slrodriguez/.claude/plans/agrega-info-tutoriales-simplificaciones-binary-gadget.md`
