import { useEffect, useState } from 'react'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import MetricTile from '../../ui/MetricTile'
import {
  simularVida, getDefaultsVida,
  EscenarioVidaIn, EscenarioVidaOut, SupuestosVidaIn, DefaultsVida,
} from '../../../api'
import VidaSupuestosForm from './VidaSupuestosForm'
import VidaEscenarioSelector from './VidaEscenarioSelector'
import VidaComparacionTable from './VidaComparacionTable'
import VidaProyeccionChart from './VidaProyeccionChart'
import ScenarioIntentBanner from '../../../help/components/ScenarioIntentBanner'
import ErrorBanner from '../../../help/components/ErrorBanner'
import { parseApiError } from '../../../help/errors/apiErrors'
import type { ParsedApiError } from '../../../help/errors/apiErrors'
import { formatUSD, formatARS } from '../../../utils'

interface Props {
  cartera: string | null
  syncVersion: number
}

const SUPUESTOS_INICIALES: SupuestosVidaIn = {
  patrimonio_inicial: 0,
  aporte_mensual: 0,
  crecimiento_anual_pct: 8,
  horizonte_meses: 120,
  moneda: 'USD',
  inflacion_anual_pct: null,
}

export default function SimuladorVida({ cartera, syncVersion }: Props) {
  const [defaults, setDefaults] = useState<DefaultsVida | null>(null)
  const [supuestos, setSupuestos] = useState<SupuestosVidaIn>(SUPUESTOS_INICIALES)
  const [seleccionados, setSeleccionados] = useState<EscenarioVidaIn[]>([
    { tipo: 'aumentar_aporte', monto: 150 },
  ])
  const [resultado, setResultado] = useState<EscenarioVidaOut | null>(null)
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState<ParsedApiError | null>(null)

  // Precarga con datos reales (patrimonio y aporte actuales). Editable: no se vuelve a pisar
  // si el usuario ya tocó el formulario, salvo que pida explícitamente "Volver a mis datos".
  useEffect(() => {
    let cancelado = false
    getDefaultsVida(cartera)
      .then(d => {
        if (cancelado) return
        setDefaults(d)
        setSupuestos(s => ({
          ...s,
          patrimonio_inicial: d.patrimonio_inicial_usd,
          aporte_mensual: d.aporte_mensual_usd ?? s.aporte_mensual,
        }))
      })
      .catch(() => {
        // Sin precarga: el formulario sigue usable con los valores iniciales.
      })
    return () => {
      cancelado = true
    }
  }, [cartera, syncVersion])

  const restaurarDefaults = () => {
    if (!defaults) return
    setSupuestos(s => ({
      ...s,
      patrimonio_inicial: defaults.patrimonio_inicial_usd,
      aporte_mensual: defaults.aporte_mensual_usd ?? 0,
    }))
  }

  const handleChangeSupuesto = <K extends keyof SupuestosVidaIn>(campo: K, valor: SupuestosVidaIn[K]) => {
    setSupuestos(s => ({ ...s, [campo]: valor }))
  }

  const handleSimular = async () => {
    setCargando(true)
    setError(null)
    try {
      const res = await simularVida(cartera, { supuestos, escenarios: seleccionados })
      setResultado(res)
    } catch (err) {
      setError(parseApiError(err))
    } finally {
      setCargando(false)
    }
  }

  const formatMonto = supuestos.moneda === 'ARS' ? formatARS : formatUSD
  const base = resultado?.resultados.find(r => r.es_base)

  return (
    <div className="space-y-4">
      <ScenarioIntentBanner variant="antes">
        {resultado?.disclaimer ?? 'Simulación matemática basada en los supuestos ingresados.'}
        {' '}No es una predicción y no modifica tus inversiones reales.
      </ScenarioIntentBanner>

      <ErrorBanner error={error} />

      <Card className="p-3 bg-app-surface-2">
        <h2 className="text-sm font-semibold text-app-text mb-3">Tus supuestos</h2>
        <VidaSupuestosForm
          supuestos={supuestos}
          onChange={handleChangeSupuesto}
          onRestaurarDefaults={restaurarDefaults}
          hayDefaults={!!defaults}
        />
      </Card>

      <div>
        <h2 className="text-sm font-semibold text-app-text mb-3">¿Qué querés probar?</h2>
        <VidaEscenarioSelector
          seleccionados={seleccionados}
          onChange={setSeleccionados}
          aporteMensualBase={supuestos.aporte_mensual}
          horizonteMeses={supuestos.horizonte_meses}
          moneda={supuestos.moneda}
        />
      </div>

      <Button onClick={handleSimular} disabled={cargando} className="w-full">
        {cargando ? 'Simulando...' : 'Simular'}
      </Button>

      {resultado && (
        <>
          {base && (
            <div className="grid grid-cols-2 gap-2">
              <MetricTile
                label="Patrimonio proyectado"
                value={formatMonto(base.metricas.patrimonio_final)}
              />
              <MetricTile
                label="Aportes acumulados"
                value={formatMonto(base.metricas.aportes_periodo)}
                infoTerm="vida_aportes_periodo"
              />
              <MetricTile
                label="Crecimiento estimado"
                value={formatMonto(base.metricas.crecimiento_estimado)}
                infoTerm="vida_crecimiento_estimado"
                tone={base.metricas.crecimiento_estimado >= 0 ? 'pos' : 'neg'}
              />
              <MetricTile
                label="Escenario base"
                value={base.nombre}
                infoTerm="vida_escenario_continuar"
              />
            </div>
          )}

          <div>
            <h2 className="text-sm font-semibold text-app-text mb-3">Evolución del patrimonio</h2>
            <Card className="p-3 bg-app-surface-2">
              <VidaProyeccionChart resultado={resultado} />
            </Card>
          </div>

          <div>
            <h2 className="text-sm font-semibold text-app-text mb-3">Comparación de escenarios</h2>
            <Card className="p-3 bg-app-surface-2">
              <VidaComparacionTable resultado={resultado} />
            </Card>
          </div>

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
    </div>
  )
}
