# Limpieza de Código - Resumen Ejecutivo

**Fecha:** 2026-08-02  
**Estado:** ✅ Completado

## Objetivo
Remover todo código viejo y no utilizado de la aplicación de inversiones, manteniendo solo la funcionalidad core de gestión de carteras de inversión.

## Cambios Realizados

### 1. Backend Python - Database Models (`database.py`)
**Removidos (no se usaban):**
- ❌ `Categoria` - Tablas relacionadas a categorización de movimientos bancarios
- ❌ `ReglaCategorizacion` - Reglas para auto-categorización
- ❌ `Movimiento` - Tabla de movimientos bancarios históricos
- ❌ `Objetivo` - Objetivos de ahorro genéricos (reemplazado por `ObjetivoInversion`)
- ❌ `ConfigJubilacion` - Configuración de jubilación
- ❌ `IndicadorEconomico` - Indicadores económicos generales

**Mantenidos (en uso):**
- ✅ `TipoCambio` - Tipo de cambio USD/ARS (fallback)
- ✅ `InstrumentoInversion` - Definiciones de acciones, bonos, fondos, etc.
- ✅ `MovimientoInversion` - Transacciones en carteras
- ✅ `PrecioInstrumento` - Histórico de precios
- ✅ `IndiceMercado` - CER y MEP (datos del Google Sheet)
- ✅ `ObjetivoInversion` - Objetivos por cartera de inversión

### 2. Backend Python - Schemas (`schemas.py`)
**Líneas removidas:** ~180 líneas

**Esquemas removidos (no tenían endpoints):**
- ❌ `CategoriaBase`, `CategoriaCreate`, `CategoriaOut`
- ❌ `ReglaBase`, `ReglaCreate`, `ReglaUpdate`, `ReglaOut`
- ❌ `MovimientoOut`, `MovimientoListOut`
- ❌ `GastoCategoria`, `SueldoHistorial`, `EvolucionPunto`, `ProyeccionPunto`
- ❌ `FileUploadResult`, `UploadResult`, `ArchivoImportado`
- ❌ `TipoCambioOut`, `CotizacionesHoyOut`, `IndicadorOut`
- ❌ `KPIsOut`, `SueldoMensual`, `DistribucionMes`, `SueldosResumenOut`
- ❌ `ObjetivoBase`, `ObjetivoCreate`, `ObjetivoUpdate`, `ObjetivoOut`, `ObjetivoOrdenUpdate`
- ❌ `ConfigJubilacionBase`, `ConfigJubilacionIn`, `ConfigJubilacionOut`

**Esquemas mantenidos:**
- ✅ `SyncErrorItem`, `SyncResult` - Resultado de sincronización con Google Sheet
- ✅ `CarteraInfo` - Información de cartera
- ✅ `InversionesResumen` - Resumen de valor e indicadores
- ✅ `ExposicionItem`, `ExposicionEje`, `ExposicionOut` - Exposición por sector/país
- ✅ `MovimientoInversionOut` - Movimientos de inversión
- ✅ `RendimientoPorTickerItem` - Rendimiento individual
- ✅ `ObjetivoInversionBase/Create/Update/Out` - Objetivos de inversión
- ✅ `AportePunto`, `AportesHistoricosOut` - Histórico de aportes

### 3. Backend Python - Services (`services/`)

**`cotizaciones.py`:**
- ✅ Simplificado: `fetch_and_cache_today()` solo valida conexión a dolarapi.com
- ✅ `get_rates_for_date()` devuelve dict vacío (fallback nunca usado)
- ❌ Removido: `convert_to_usd()` - No se usaba

**`inversiones_analytics.py`:**
- ❌ Removido: `_ipc_indice()` - Función interna no usada (no hay datos de IPC en el Sheet)

### 4. Frontend TypeScript - API Functions (`src/api/index.ts`)
**Líneas removidas:** ~330 líneas

**Interfaces TypeScript removidas:**
- ❌ `KPIs`, `EvolucionPunto`, `GastoCategoria`, `SueldoHistorial`
- ❌ `Movimiento`, `MovimientoList`, `Categoria`, `Regla`
- ❌ `TipoCambio`, `CotizacionesHoy`, `Indicador`
- ❌ `ProyeccionPunto`, `FileUploadResult`, `UploadResult`, `ArchivoImportado`
- ❌ `Objetivo`, `ObjetivoPayload`, `ConfigJubilacion`, `ConfigJubilacionPayload`
- ❌ `SueldoMensual`, `DistribucionMes`, `SueldosResumenOut`, `MetodoProyeccion`

**Funciones de API removidas (28 funciones):**
- ❌ `getKPIs`, `getEvolucion`, `getGastosPorCategoria`, `getEvolucionSueldo`, `getSueldosResumen`
- ❌ `getMovimientos`, `getCategorias`, `createCategoria`
- ❌ `getReglas`, `createRegla`, `updateRegla`, `deleteRegla`, `recategorizar`
- ❌ `getCotizaciones`, `getCotizacionesHistorico`
- ❌ `getIndicadores`, `getIndicadoresHistorico`
- ❌ `getMetodosProyeccion`, `getProyecciones`, `uploadCSVs`
- ❌ `getObjetivos`, `createObjetivo`, `updateObjetivo`, `deleteObjetivo`, `updateOrdenObjetivo`
- ❌ `getConfigJubilacion`, `upsertConfigJubilacion`, `getArchivos`

**Funciones mantenidas:**
- ✅ `syncInversiones` - Sincronizar desde Google Sheet
- ✅ `getCarterasInversion` - Listar carteras
- ✅ `getResumenInversiones` - Resumen de cartera
- ✅ `getExposicionInversiones` - Exposición
- ✅ `getMovimientosInversion` - Movimientos
- ✅ `getRendimientoPorTicker` - Rendimiento por ticker
- ✅ `getObjetivoInversion` - Objetivo de inversión
- ✅ `getAportesHistoricos` - Histórico de aportes
- ✅ `crearObjetivoInversion`, `editarObjetivoInversion`, `eliminarObjetivoInversion`

## Estadísticas de Limpieza

| Métrica | Cantidad |
|---------|----------|
| Modelos de BD removidos | 6 |
| Esquemas Pydantic removidos | 22+ |
| Funciones de API Frontend removidas | 28 |
| Interfaces TypeScript removidas | 23+ |
| Funciones de servicio removidas | 2 |
| Líneas de código Python eliminadas | ~250 |
| Líneas de código TypeScript eliminadas | ~330 |
| **Total de líneas removidas** | **~580** |

## Validación

✅ **Python:** Todos los imports se resuelven sin errores  
✅ **TypeScript:** Estructura sin referencias rotas  
✅ **Routers:** Los 2 routers activos siguen completamente funcionales  
✅ **Frontend:** Componentes de inversiones intactos  

## Lo que se mantiene (100% activo)

### Backend Routers
- `inversiones.py` - 13 endpoints de inversiones
- `objetivos_inversion.py` - 4 endpoints de objetivos

### Frontend
- `pages/Inversiones.tsx` - Página principal
- `hooks/useInversiones.ts` - Estado global
- `hooks/useObjetivoInversion.ts` - Estado de objetivos
- 9 componentes React relacionados a inversiones
- `utils.ts` - Utilidades de formato

## Beneficios

1. **Reducción de deuda técnica:** -580 líneas de código muerto
2. **Claridad:** Codebase 100% enfocada en inversiones
3. **Mantenibilidad:** Menos superficie de ataque, menos código a testear
4. **Performance:** Menos imports innecesarios
5. **Onboarding:** Más fácil entender qué hace la app

## Próximos pasos (opcionales)

1. Remover tablas abandonadas de la base de datos existente (hacer migration)
2. Documentar las decisiones de diseño en un README
3. Considerar agregar suites de pruebas unitarias
