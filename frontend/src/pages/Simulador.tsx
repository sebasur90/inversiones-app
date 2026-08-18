import { useEffect, useState } from 'react'
import { useInversionesContext } from '../context/InversionesContext'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import {
  simularEscenarios,
  listarEscenarios,
  guardarEscenario,
  EscenarioSimulacionRequest,
  EscenarioSimulacionItem,
  EscenarioSimulacionOut,
  EscenarioParamsIn,
  Escenario,
} from '../api'
import EscenarioConfigPanel from '../components/inversiones/EscenarioConfigPanel'
import EscenarioProyeccionChart from '../components/inversiones/EscenarioProyeccionChart'
import EscenarioComparacionTable from '../components/inversiones/EscenarioComparacionTable'

export default function Simulador() {
  const { carteraSeleccionada } = useInversionesContext()

  // Estados
  const [escenarios, setEscenarios] = useState<EscenarioSimulacionItem[]>([
    { tipo_preset: 'personalizado', nombre: 'Base', parametros: undefined },
    { tipo_preset: 'alcista', nombre: 'Alcista', parametros: undefined },
    { tipo_preset: 'bajista', nombre: 'Bajista', parametros: undefined },
  ])
  const [resultado, setResultado] = useState<EscenarioSimulacionOut | null>(null)
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [escenariosSaved, setEscenariosSaved] = useState<Escenario[]>([])
  const [mostrarConfigPersonalizado, setMostrarConfigPersonalizado] = useState(false)

  // Cargar escenarios guardados
  useEffect(() => {
    let cancelado = false
    const fetchEscenarios = async () => {
      try {
        const saved = await listarEscenarios(carteraSeleccionada)
        if (!cancelado) {
          setEscenariosSaved(saved)
        }
      } catch (err) {
        // Silenciar error (lista vacía esperada en primera carga)
      }
    }
    fetchEscenarios()
    return () => {
      cancelado = true
    }
  }, [carteraSeleccionada])

  // Simular
  const handleSimular = async () => {
    // Validación: 'personalizado' requiere parámetros
    for (const esc of escenarios) {
      if (esc.tipo_preset === 'personalizado' && !esc.parametros) {
        setError("Escenarios 'personalizado' requieren configurar los parámetros")
        return
      }
    }

    setCargando(true)
    setError(null)
    try {
      const body: EscenarioSimulacionRequest = { escenarios }
      const res = await simularEscenarios(carteraSeleccionada, body)
      setResultado(res)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Error en la simulación')
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
      setError('Configura los parámetros antes de guardar')
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
    } catch (err: any) {
      let mensajeError = 'Error al guardar'
      if (err?.response?.data?.detail) {
        mensajeError = typeof err.response.data.detail === 'string'
          ? err.response.data.detail
          : JSON.stringify(err.response.data.detail)
      }
      setError(mensajeError)
    }
  }

  return (
    <div className="pb-8">
      <ScreenHeader title="Simulador de escenarios" onBack={() => history.back()} />

      <div className="px-3 space-y-4">
        {/* Advertencia: Simulado */}
        <Card className="bg-app-surface border border-app-gold/30 p-3">
          <div className="flex items-start gap-2">
            <span className="text-xl">⚠️</span>
            <div>
              <div className="font-medium text-app-gold text-sm">Simulación determinista</div>
              <div className="text-xs text-app-text-secondary mt-1">
                Estos resultados son proyecciones bajo supuestos fijos. No representan predicciones de mercado.
              </div>
            </div>
          </div>
        </Card>

        {/* Error */}
        {error && (
          <Card className="bg-red-900/20 border border-red-600/30 p-3">
            <div className="text-sm text-red-300">{error}</div>
          </Card>
        )}

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

        {/* Escenarios guardados (futuro) */}
        {escenariosSaved.length > 0 && (
          <Card className="p-3 border border-app-border">
            <div className="text-xs font-medium text-app-text-secondary mb-2">
              Escenarios guardados ({escenariosSaved.length})
            </div>
            <div className="space-y-1">
              {escenariosSaved.map(esc => (
                <div key={esc.id} className="text-xs text-app-text py-1 border-b border-app-border last:border-0">
                  {esc.nombre}
                  <span className="text-app-text-secondary ml-2">({esc.tipo_preset})</span>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    </div>
  )
}
