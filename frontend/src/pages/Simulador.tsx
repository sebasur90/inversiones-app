import { useEffect, useState } from 'react'
import { useInversionesContext } from '../context/InversionesContext'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import {
  simularEscenarios,
  listarEscenarios,
  guardarEscenario,
  duplicarEscenario,
  eliminarEscenario,
  getRendimientoPorTicker,
  getMovimientosInversion,
  EscenarioSimulacionRequest,
  EscenarioSimulacionItem,
  EscenarioSimulacionOut,
  EscenarioParamsIn,
  Escenario,
} from '../api'
import EscenarioConfigPanel from '../components/inversiones/EscenarioConfigPanel'
import EscenarioProyeccionChart from '../components/inversiones/EscenarioProyeccionChart'
import EscenarioComparacionTable from '../components/inversiones/EscenarioComparacionTable'
import ScenarioIntentBanner from '../help/components/ScenarioIntentBanner'
import ErrorBanner from '../help/components/ErrorBanner'
import ResultInterpretation from '../help/components/ResultInterpretation'
import { parseApiError } from '../help/errors/apiErrors'
import type { ParsedApiError } from '../help/errors/apiErrors'

export default function Simulador() {
  const { carteraSeleccionada, syncVersion } = useInversionesContext()

  // Estado inicial con parámetros completos por defecto
  const defaultParams: EscenarioParamsIn = {
    horizonte_meses: 60,
    variacion_dolar_pct: 0,
    variacion_por_instrumento: {},
    variacion_por_defecto_pct: 0,
    aporte_mensual_usd: 0,
    crecimiento_aporte_anual_pct: 0,
    retiro_mensual_usd: 0,
    modo_dividendos: 'reinvertir_total',
    dividend_yield_anual_pct: 0,
    pct_dividendo_reinvertido: null,
    comision_pct: 0,
    inflacion_anual_pct: null,
  }

  // Estados
  const [escenarios, setEscenarios] = useState<EscenarioSimulacionItem[]>([
    { tipo_preset: 'personalizado', nombre: 'Base', parametros: defaultParams },
    { tipo_preset: 'alcista', nombre: 'Alcista', parametros: defaultParams },
    { tipo_preset: 'bajista', nombre: 'Bajista', parametros: defaultParams },
  ])
  const [resultado, setResultado] = useState<EscenarioSimulacionOut | null>(null)
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState<ParsedApiError | null>(null)
  const [escenariosSaved, setEscenariosSaved] = useState<Escenario[]>([])
  const [tickersDisponibles, setTickersDisponibles] = useState<{ ticker: string; nombre: string }[]>([])
  const [mostrarConfigPersonalizado, setMostrarConfigPersonalizado] = useState(false)
  const [confirmandoEliminar, setConfirmandoEliminar] = useState<number | null>(null)

  // Cargar escenarios guardados + tickers en cartera
  useEffect(() => {
    let cancelado = false
    const fetchData = async () => {
      try {
        const [saved, rendimiento, movimientos] = await Promise.all([
          listarEscenarios(carteraSeleccionada),
          getRendimientoPorTicker(carteraSeleccionada).catch(() => []),
          getMovimientosInversion(carteraSeleccionada ? { cartera: carteraSeleccionada } : {}).catch(() => []),
        ])
        if (cancelado) return
        setEscenariosSaved(saved)

        // B14: `getRendimientoPorTicker` descarta las posiciones sin cotización cargada, así que
        // esas no se podrían override-ear. Se une con las tenencias derivadas de los movimientos.
        const tenencia = new Map<string, number>()
        for (const m of movimientos) {
          const q = m.cantidad ?? 0
          const signo = m.tipo_movimiento === 'compra' ? 1
            : (m.tipo_movimiento === 'venta' || m.tipo_movimiento === 'amortizacion') ? -1 : 0
          tenencia.set(m.ticker, (tenencia.get(m.ticker) ?? 0) + signo * q)
        }
        const nombrePorTicker = new Map(rendimiento.map(r => [r.ticker, r.nombre]))
        const universo = new Set<string>([
          ...rendimiento.filter(r => r.cantidad_actual > 0).map(r => r.ticker),
          ...[...tenencia.entries()].filter(([, q]) => q > 1e-9).map(([t]) => t),
        ])
        setTickersDisponibles(
          [...universo]
            .map(t => ({ ticker: t, nombre: nombrePorTicker.get(t) ?? t }))
            .sort((a, b) => a.ticker.localeCompare(b.ticker)),
        )
      } catch (err) {
        // Silenciar error (lista vacía esperada en primera carga)
      }
    }
    fetchData()
    return () => {
      cancelado = true
    }
  }, [carteraSeleccionada, syncVersion])

  const recargarGuardados = async () => {
    try {
      setEscenariosSaved(await listarEscenarios(carteraSeleccionada))
    } catch (err) {
      setError(parseApiError(err))
    }
  }

  // Cargar un escenario guardado como panel editable
  const handleCargarGuardado = (esc: Escenario) => {
    setEscenarios(prev => {
      if (prev.length >= 6) return prev
      return [...prev, { tipo_preset: 'personalizado', nombre: esc.nombre, parametros: esc.parametros }]
    })
  }

  const handleDuplicarGuardado = async (esc: Escenario) => {
    try {
      await duplicarEscenario(esc.id, `${esc.nombre} (copia)`)
      await recargarGuardados()
      setError(null)
    } catch (err) {
      setError(parseApiError(err))
    }
  }

  // B13: eliminar es irreversible → requiere un segundo click ("¿Eliminar?"), con timeout.
  const handleEliminarGuardado = async (esc: Escenario) => {
    if (confirmandoEliminar !== esc.id) {
      setConfirmandoEliminar(esc.id)
      window.setTimeout(() => {
        setConfirmandoEliminar(prev => (prev === esc.id ? null : prev))
      }, 3000)
      return
    }
    setConfirmandoEliminar(null)
    try {
      await eliminarEscenario(esc.id)
      await recargarGuardados()
      setError(null)
    } catch (err) {
      setError(parseApiError(err))
    }
  }

  // Simular
  const handleSimular = async () => {
    // Validación: 'personalizado' requiere parámetros
    for (const esc of escenarios) {
      if (esc.tipo_preset === 'personalizado' && !esc.parametros) {
        setError({ message: "Escenarios 'personalizado' requieren configurar los parámetros" })
        return
      }
    }

    setCargando(true)
    setError(null)
    try {
      const body: EscenarioSimulacionRequest = { escenarios }
      const res = await simularEscenarios(carteraSeleccionada, body)
      setResultado(res)
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setCargando(false)
    }
  }

  // Cambiar parámetro de escenario
  const handleChangeEscenario = (index: number, campo: string, valor: any) => {
    setEscenarios(prev => {
      const updated = [...prev]
      const item = { ...updated[index] }
      const params = item.parametros || {
        horizonte_meses: 60,
        variacion_dolar_pct: 0,
        variacion_por_instrumento: {},
        variacion_por_defecto_pct: 0,
        aporte_mensual_usd: 0,
        crecimiento_aporte_anual_pct: 0,
        retiro_mensual_usd: 0,
        modo_dividendos: 'reinvertir_total',
        dividend_yield_anual_pct: 0,
        pct_dividendo_reinvertido: null,
        comision_pct: 0,
        inflacion_anual_pct: null,
      } as EscenarioParamsIn
      item.parametros = { ...params, [campo]: valor }
      updated[index] = item
      return updated
    })
  }

  // Guardar escenario
  const handleGuardarEscenario = async (escenarioIndex: number) => {
    const esc = escenarios[escenarioIndex]
    if (!esc.parametros) {
      setError({ message: 'Configura los parámetros antes de guardar' })
      return
    }

    try {
      const nombre = esc.nombre || `Escenario ${new Date().toLocaleString()}`
      // Asegurar que todos los parámetros requeridos estén presentes
      const parametrosCompletos: EscenarioParamsIn = {
        horizonte_meses: esc.parametros.horizonte_meses || 60,
        variacion_dolar_pct: esc.parametros.variacion_dolar_pct ?? 0,
        variacion_por_instrumento: esc.parametros.variacion_por_instrumento || {},
        variacion_por_defecto_pct: esc.parametros.variacion_por_defecto_pct ?? 0,
        aporte_mensual_usd: esc.parametros.aporte_mensual_usd ?? 0,
        crecimiento_aporte_anual_pct: esc.parametros.crecimiento_aporte_anual_pct ?? 0,
        retiro_mensual_usd: esc.parametros.retiro_mensual_usd ?? 0,
        modo_dividendos: esc.parametros.modo_dividendos || 'reinvertir_total',
        dividend_yield_anual_pct: esc.parametros.dividend_yield_anual_pct ?? 0,
        pct_dividendo_reinvertido: esc.parametros.pct_dividendo_reinvertido ?? null,
        comision_pct: esc.parametros.comision_pct ?? 0,
        inflacion_anual_pct: esc.parametros.inflacion_anual_pct ?? null,
      }
      await guardarEscenario({
        cartera: carteraSeleccionada,
        nombre,
        tipo_preset: esc.tipo_preset,
        parametros: parametrosCompletos,
      })
      // Recargar lista
      const saved = await listarEscenarios(carteraSeleccionada)
      setEscenariosSaved(saved)
      setError(null) // Limpiar error al éxito
    } catch (err) {
      setError(parseApiError(err))
    }
  }

  return (
    <div className="pb-8">
      <ScreenHeader title="Simulador de escenarios" onBack={() => history.back()} />

      <div className="px-3 space-y-4">
        {/* Advertencia: Simulado */}
        <ScenarioIntentBanner variant="antes">
          Estos resultados son proyecciones bajo supuestos fijos. No representan predicciones de mercado ni modifican tus inversiones reales.
        </ScenarioIntentBanner>

        {/* Error */}
        <ErrorBanner error={error} />

        {/* Panel de configuración — 3 escenarios lado a lado */}
        <div>
          <h2 className="text-sm font-semibold text-app-text mb-3">Escenarios</h2>
          <div className="space-y-3">
            {escenarios.map((esc, idx) => (
              <EscenarioConfigPanel
                key={idx}
                escenario={esc}
                index={idx}
                onChangePreset={(tipo: string) => {
                  const updated = [...escenarios]
                  const tipoPreset = tipo as 'alcista' | 'bajista' | 'crisis' | 'personalizado'
                  // Si selecciona 'personalizado', inicializar parámetros si no existen
                  let parametros = undefined
                  if (tipoPreset === 'personalizado' && !esc.parametros) {
                    parametros = {
                      horizonte_meses: 60,
                      variacion_dolar_pct: 0,
                      variacion_por_instrumento: {},
                      variacion_por_defecto_pct: 0,
                      aporte_mensual_usd: 0,
                      crecimiento_aporte_anual_pct: 0,
                      retiro_mensual_usd: 0,
                      modo_dividendos: 'reinvertir_total',
                      dividend_yield_anual_pct: 0,
                      pct_dividendo_reinvertido: null,
                      comision_pct: 0,
                      inflacion_anual_pct: null,
                    } as EscenarioParamsIn
                  }
                  updated[idx] = { ...esc, tipo_preset: tipoPreset, parametros }
                  setEscenarios(updated)
                }}
                onChangeParam={(campo, valor) => handleChangeEscenario(idx, campo, valor)}
                onSave={() => handleGuardarEscenario(idx)}
                tickersDisponibles={tickersDisponibles}
              />
            ))}
          </div>
        </div>

        {/* Botón simular */}
        <Button
          onClick={handleSimular}
          disabled={cargando}
          className="w-full"
        >
          {cargando ? 'Simulando...' : 'Simular'}
        </Button>

        {/* Resultados */}
        {resultado && (
          <>
            {/* Gráfico */}
            <div className="mt-6">
              <h2 className="text-sm font-semibold text-app-text mb-3">Evolución del patrimonio</h2>
              <Card className="p-3 bg-app-surface-2">
                <EscenarioProyeccionChart resultado={resultado} />
              </Card>
            </div>

            {/* Tabla comparativa */}
            <div className="mt-6">
              <h2 className="text-sm font-semibold text-app-text mb-3">Comparación de escenarios</h2>
              <Card className="p-3 bg-app-surface-2">
                <EscenarioComparacionTable resultado={resultado} />
              </Card>
            </div>

            {/* Interpretación */}
            <ResultInterpretation>
              <p>Cada escenario muestra cómo evolucionaría tu patrimonio bajo diferentes supuestos de mercado. Compara los valores finales para entender el rango de posibilidades.</p>
              <p className="text-app-text-faint text-label">Recuerda: estos son ejercicios matemáticos bajo supuestos. El mercado real es más complejo y menos predecible.</p>
            </ResultInterpretation>

            {/* Advertencias */}
            {resultado.advertencias.length > 0 && (
              <Card className="p-3 bg-yellow-900/20 border border-yellow-600/30">
                <div className="text-xs space-y-1">
                  {resultado.advertencias.map((adv, idx) => (
                    <div key={idx} className="text-yellow-200">• {adv}</div>
                  ))}
                </div>
              </Card>
            )}
          </>
        )}

        {/* Escenarios guardados */}
        {escenariosSaved.length > 0 && (
          <Card className="p-3 border border-app-border">
            <div className="text-xs font-medium text-app-text-secondary mb-2">
              Escenarios guardados ({escenariosSaved.length})
            </div>
            <div className="space-y-1">
              {escenariosSaved.map(esc => (
                <div
                  key={esc.id}
                  className="flex items-center gap-2 text-xs text-app-text py-1.5 border-b border-app-border last:border-0"
                >
                  <div className="flex-1 min-w-0 truncate">
                    {esc.nombre}
                    <span className="text-app-text-secondary ml-2">({esc.tipo_preset})</span>
                  </div>
                  <button
                    onClick={() => handleCargarGuardado(esc)}
                    disabled={escenarios.length >= 6}
                    className="text-label font-semibold text-app-gold disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Cargar
                  </button>
                  <button
                    onClick={() => handleDuplicarGuardado(esc)}
                    className="text-label font-semibold text-app-text-secondary hover:text-app-text"
                  >
                    Duplicar
                  </button>
                  <button
                    onClick={() => handleEliminarGuardado(esc)}
                    className={`text-label font-semibold ${
                      confirmandoEliminar === esc.id
                        ? 'text-app-coral'
                        : 'text-app-text-secondary hover:text-app-coral'
                    }`}
                  >
                    {confirmandoEliminar === esc.id ? '¿Eliminar?' : 'Eliminar'}
                  </button>
                </div>
              ))}
            </div>
            {escenarios.length >= 6 && (
              <div className="text-label text-app-text-faint mt-2">
                Máximo de 6 paneles de escenario. Quitá alguno para cargar otro.
              </div>
            )}
          </Card>
        )}
      </div>
    </div>
  )
}
