# Sistema de Ayuda Contextual — Referencia

Este directorio centraliza todo el contenido y componentes del sistema de ayuda contextual de la app.

## Estructura

- **`types.ts`** — Definición de `HelpContent` y alias `HelpKey`
- **`content/`** — Contenido editable (separado de presentación)
  - `glosario.ts` — 31 términos del glosario fallback (no enriquecidos)
  - `simulador.ts` — 12 keys para Piloto A (Simulador de escenarios)
  - `objetivo.ts` — 9 keys para Piloto B (Objetivo/Proyección)
  - `benchmarks.ts` — 4 keys para Piloto C (Benchmarks)
  - `patrimonio.ts` — 5 keys para Patrimonio (Batch 1)
  - `index.ts` — Combina todo en un Record único
- **`components/`** — Componentes reutilizables
  - `InfoTooltip.tsx` — Reemplaza `InfoTerm`, botón "(i)" + Modal con secciones
  - `FormHelp.tsx` — Wrapper sobre InfoTooltip + rango de validación
  - `ScenarioIntentBanner.tsx` — Callout "¿Qué estás haciendo?" / "¿Qué vas a obtener?"
  - `ResultInterpretation.tsx` — Bloque "🔎 Interpretación" post-resultado
  - `ErrorBanner.tsx` — Presentación visual de ParsedApiError
- **`errors/`** — Manejo de errores amigables
  - `escenarioLimits.ts` — Espejo de límites de `backend/app/schemas.py` (fuente única de verdad en frontend)
  - `apiErrors.ts` — `parseApiError()` que maneja errores Pydantic y customizados

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
| Exposición | ⏳ | — | |
| Movimientos | ⏳ | — | |
| Posiciones | ⏳ | — | |
| Precios | ⏳ | — | |
| IndicadoresMacro | ⏳ | — | |
| Vencimientos | ⏳ | — | |
| Comparador | ⏳ | — | |
| Comisiones | ⏳ | — | |
| Patrimonio | ✅ | ✓ | MetricTile + patrimonio.ts + ErrorBanner (Batch 1) |
| Rebalanceo | ⏳ | — | |
| Riesgo | ✅ | ✓ | MetricTile + ErrorBanner + InfoTooltip; reutiliza glosario (Batch 1) |
| PerformanceRelativa | ⏳ | — | |
| Diagnostico | ✅ | ✓ | ErrorBanner + InfoTooltip para salud/dimensiones; 6 términos (Batch 2) |
| CalidadDatos | ✅ | ✓ | InfoTooltip para health_score/errores/advertencias; 5 términos (Batch 2) |
| Resumen | ✅ | ✓ | InfoTooltip + ErrorBanner en diagnóstico/calidad (Batch 1) |
| Tabs de TickerDetalle | ⏳ | — | |

## Notas para mantainers

- **Cambios en backend de validación**: actualizar `escenarioLimits.ts` línea que apunta a `backend/app/schemas.py:136-149`
- **Cambios en `MetricCard.tsx` original**: verificar que no hay otros consumidores con `grep -rl "ui/MetricCard"` antes de eliminar
- **EmptyState.tsx**: no se toca en este rollout salvo necesidad puntual
- **Modo guía/tours/centro de ayuda**: diferidos a Fase 2, sin diseño adicional aquí

## Referencias

- Plan original: `/home/slrodriguez/.claude/plans/sistema-de-peaceful-quasar.md`
- Estado de implementación: `/home/slrodriguez/.claude/projects/-home-slrodriguez-inversiones-app/memory/plan_ayuda_fase1_avance.md`
